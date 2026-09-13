#!/usr/bin/env python3
"""
remove-fillers.py — transcreve com timestamp por palavra e acha candidatos a corte

Script da skill /cut-silence (modo --fillers).

O SCRIPT MEDE, O AGENTE JULGA. Este script nao decide nada sobre a fala. Ele
entrega medicao:

  1. extrai audio e transcreve com timestamp por palavra
  2. anota, por palavra, a pausa antes dela e a confianca do ASR
  3. escreve tudo num JSON

Quem le esse JSON, corrige a transcricao e decide o que cortar — vicio, gagueira,
recomeco de take, palavra truncada — e o agente (Claude Code), seguindo o passo
5b do SKILL.md.

Houve detector de gagueira e de recomeco aqui dentro. Sairam. "Isso e gagueira?"
e "ele recomecou a frase?" sao perguntas SEMANTICAS: em portugues falado
"o que que eu faco" e construcao normal, e nenhuma comparacao de palavras
identicas distingue isso de "eu eu acho". A busca de recomeco chegou a oito
parametros calibrados e ainda errava. Regra escrita num SKILL.md envelhece
melhor que numero calibrado contra um arquivo.

O texto deste script fica em portugues de proposito: o modo --fillers nasceu
calibrado em PT-BR. O resto do repositorio e em ingles.

Uso:
  python remove-fillers.py <video.mp4> [--json <saida.json>] [--modelo <id>]
  python remove-fillers.py --aplicar <video.mp4> <cortes.json> <saida.mp4> [--margin 0.2s]
  python remove-fillers.py --autoteste

Requisitos:
  pip install auto-editor ffmpeg-normalize
  ffmpeg e ffprobe no PATH
  OPENROUTER_API_KEY: variavel de ambiente, ou num .env ao lado do script
                      (ou em qualquer pasta acima dele)

Este arquivo e autocontido de proposito: a skill precisa funcionar copiada
sozinha para outra maquina, entao nao importa nada de fora da propria pasta.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Deepgram gera o tempo da palavra direto do modelo acustico, quadro a quadro.
# O Whisper deriva por DTW sobre cross-attention, que varia 100-400ms para o
# mesmo audio — erro suficiente para o corte comer o ataque da palavra vizinha.
STT_MODEL  = "deepgram/nova-3"
OPENROUTER = "https://openrouter.ai/api/v1"

# $ por minuto de audio, para estimar antes de gastar. Fonte: tabela publica do
# OpenRouter. Atualize junto se trocar de modelo; valor ausente vira "?" no aviso.
PRECO_MIN = {
    "deepgram/nova-3":                  0.0043,
    "microsoft/mai-transcribe-2":       0.001667,   # $0.10/hora
    "openai/whisper-large-v3-turbo":    0.00018,    # $0.000003/seg
    "openai/whisper-large-v3":          0.00048,    # $0.000008/seg
    "nvidia/parakeet-tdt-0.6b-v3":      0.0015,
    "openai/whisper-1":                 0.006,
}

MAX_MB        = 15          # base64 incha ~33%, entao 15MB cru ~ 20MB no request
CHUNK_MINUTES = 18

# O SCRIPT MEDE. O AGENTE JULGA.
#
# Aqui nao ha mais nenhum detector de gagueira nem de recomeco de take. Houve, e
# a conta ficou cara: a busca de recomeco chegou a OITO parametros (tamanho de
# sonda, limiar, janela, minimo de caracteres, teto de duracao, empate, recuo,
# pausa), cada um nascido de uma falha especifica, e ainda assim errava. A busca
# de gagueira era menor e mais honesta, mas rejeitava 10 dos 13 achados num
# arquivo real: em portugues falado "o que que eu faco" e construcao normal, nao
# gagueira, e nenhuma comparacao de palavras identicas vai saber a diferenca.
#
# As duas perguntas — "isso e gagueira?", "ele recomecou a frase?" — sao
# SEMANTICAS. Quem le o texto responde; quem compara caracteres aproxima.
#
# Entao o script entrega medicao, e so medicao:
#
#   start / end     fronteira da palavra
#   gap_antes       o silencio antes dela. Quem recomeca para antes de
#                   recomecar, e essa pausa some numa transcricao em texto
#                   corrido — e o unico sinal que ler o texto nao recupera
#   conf            confianca do ASR naquela palavra. Palavra truncada no meio
#                   da silaba ("É mu... É muito grande") volta como fragmento
#                   sem sentido e com confianca baixa: e assim que se acha um
#                   tipo de gagueira que nenhuma comparacao de texto pega
#
# O julgamento vive no SKILL.md, que e onde da para escrever uma regra em vez de
# calibrar um numero.

PAD_CORTE_S = 0.06          # folga no corte de palavra; ver faixa_palavra()

# ── encaixe do corte no vale de energia ──────────────────────────────────────
# A fronteira que o ASR devolve ("a palavra ok vai de 149.04 a 149.20") e uma
# ESTIMATIVA. Errando tres centesimos, sobra pedaco de palavra — foi o "ok"
# cortado no meio que o usuario ouviu. Editor humano nao corta onde a palavra
# termina: corta onde a onda esta mais baixa por perto, no vale entre os sons.
#
# Entao cada fronteira desliza ate o minimo local de energia. Isso nao depende
# mais da precisao do modelo de transcricao — a decisao final sai do audio.
JANELA_SNAP_S = 0.15        # quanto a fronteira pode deslizar, para cada lado
PASSO_RMS_S   = 0.01        # resolucao da curva de energia

# ── respiro variavel ─────────────────────────────────────────────────────────
# Uma margem unica para o video inteiro nao existe na edicao de verdade. Editor
# nenhum corta igual em todo lugar:
#
#   dentro da frase       quase nada        e so respiracao entre palavras
#   entre duas frases     um pouco          a pausa e a pontuacao
#   virada de assunto     bastante          a pausa E o paragrafo
#
# Margem apertada no video todo picota a aula (0.1s deixou o usuario com
# "corte no meio da conversa"); margem larga no video todo deixa arrastado.
#
# A transcricao ja sabe onde cada frase acaba: a palavra vem pontuada ("agora?",
# "coisas."). Entao a margem base fica apertada e estes respiros sao devolvidos
# so nas fronteiras, via --add-in do auto-editor.
RESPIRO_FRASE   = 0.35      # apos . ? !
RESPIRO_TOPICO  = 0.60      # apos fim de frase seguido de pausa longa
PAUSA_TOPICO    = 0.80      # a partir daqui, o locutor mudou de assunto
FIM_DE_FRASE    = ".?!"

RAM_MINIMA_MB = 1800        # abaixo disso o encode costuma nem iniciar

CORTE_SUSPEITO_PCT = 0.70   # acima disso o corte comeu fala, nao silencio
CORTE_IRRELEVANTE_PCT = 0.02  # abaixo disso nao valeu o re-encode

# -14 LUFS, nao -16. O YouTube SO ABAIXA volume: ele normaliza upload alto para
# ~-14 e deixa conteudo mais baixo quieto. Entregar a -16 e escolher tocar mais
# baixo que todo o resto do feed, para sempre. -16 e padrao de podcast.
ALVO_LUFS = -14.0

# Miramos acima do alvo porque o limiter come ~0.5 LU ao aparar os transientes.
MARGEM_LIMITER = 0.5

# Teto de amostra do limiter, linear. 0.89 ~= -1.0 dBFS.
TETO_LINEAR = 0.89

# Quanto o resultado medido pode se afastar do alvo antes de virar aviso.
TOLERANCIA_LU = 1.0

# POR QUE NAO USAMOS MAIS --auto-lower-loudness-target.
#
# Aquela flag garante ganho LINEAR puro: nada de dinamica tocada. O preco e que,
# quando o ganho necessario estouraria o teto de pico, ela desiste do alvo em
# silencio — e o quanto ela desiste varia por arquivo.
#
# Medido num lote real de 18 aulas: gravacoes com crest factor de ~22 dB (clique
# de mouse e teclado por cima de fala baixa) sairam entre -17.8 e -27.1 LUFS com
# alvo de -14. O arquivo mais baixo precisava de 30 dB de ganho; aos 21 dB o pico
# ja batia no teto. Todos os 18 colaram no teto de pico, cada um num loudness
# diferente — ou seja, a normalizacao destruiu justamente a consistencia que ela
# existe para dar.
#
# A skill prometia "-14 LUFS" E "linear, sem compressao". Nessas fontes as duas
# promessas sao incompativeis, e a antiga abandonava a primeira sem avisar.
#
# A escolha agora e explicita: ganho linear + LIMITER DE PICO. Um limiter nao e
# um compressor — ele apara o transiente (o clique) e nao encosta na dinamica da
# fala, que e o que a promessa original queria proteger. E o resultado e SEMPRE
# medido no arquivo final: se ficar a mais de TOLERANCIA_LU do alvo, a skill diz,
# em vez de reportar o numero que ela pediu e nao conseguiu cumprir.

# Os tres ultimos valores vieram de um falso positivo real, nao de teoria.
# Num video de 1.1 min, "e cada" (8.96s) casou com "cada um" (45.48s) a 0.727,
# so por compartilhar "cada", e propos cortar 36,5 SEGUNDOS de narracao boa.
# Recomeco de take de verdade dura segundos e casa com folga: o caso que motivou
def _norm(s: str) -> str:
    return re.sub(r"[^\wáàâãéêíóôõúüç]", "", s.lower().strip())


# ── infra (autocontida: nada daqui pode depender de arquivo fora da skill) ────

def _chave_no_env(env: Path):
    """Le SOMENTE OPENROUTER_API_KEY de um .env. Devolve o valor, ou None.

    A skill costuma ser instalada dentro do projeto de outra pessoa, e o .env
    desse projeto tende a estar cheio de credencial que nao tem nada a ver com
    corte de video. Nao ha motivo para carregar nada disso no processo.

    Le como utf-8-sig, nao utf-8: no Windows, Bloco de Notas e `Out-File
    -Encoding utf8` gravam BOM. Com utf-8 puro a primeira chave do arquivo vira
    "﻿OPENROUTER_API_KEY" e nunca casa com o nome — falha invisivel, porque
    o arquivo parece perfeito em qualquer editor.
    """
    for linha in env.read_text(encoding="utf-8-sig").splitlines():
        if linha.lstrip().startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        if k.strip() != "OPENROUTER_API_KEY":
            continue
        v = v.strip().strip('"').strip("'")
        if v:                       # o .env.example tem a chave vazia
            return v
    return None


def carregar_env():
    """Procura a chave no ambiente; se nao achar, varre .env subindo as pastas."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return
    partidas = [Path(__file__).resolve().parent, Path.cwd()]
    vistos = set()
    for partida in partidas:
        for pasta in [partida, *partida.parents]:
            env = pasta / ".env"
            if env in vistos or not env.exists():
                vistos.add(env)
                continue
            vistos.add(env)
            chave = _chave_no_env(env)
            if chave:
                os.environ["OPENROUTER_API_KEY"] = chave
                return


def slugify(texto: str, max_len: int = 50) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s-]", "", texto.lower())
    texto = re.sub(r"[\s_]+", "-", texto)
    return re.sub(r"-+", "-", texto).strip("-")[:max_len] or "video"


def extract_audio(video: Path, destino: Path):
    subprocess.run(["ffmpeg", "-y", "-i", str(video), "-vn", "-ar", "16000",
                    "-ac", "1", "-b:a", "64k", str(destino)],
                   check=True, capture_output=True)


def get_duration(caminho: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(caminho)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def extract_chunk(origem: Path, destino: Path, inicio: float, duracao: float):
    subprocess.run(["ffmpeg", "-y", "-i", str(origem), "-ss", str(inicio),
                    "-t", str(duracao), "-acodec", "copy", str(destino)],
                   check=True, capture_output=True)


def ram_livre_mb():
    """MB de RAM disponivel, ou None se nao der para medir nesta plataforma."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            ms = _Mem()
            ms.dwLength = ctypes.sizeof(_Mem)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return None
            return ms.ullAvailPhys / 1_048_576
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for linha in meminfo.read_text().splitlines():
                if linha.startswith("MemAvailable:"):
                    return int(linha.split()[1]) / 1024
    except Exception:                       # noqa: BLE001 — medir RAM nunca pode quebrar o corte
        return None
    return None


def aviso_de_ram():
    """Avisa se a RAM livre nao comporta o encode. Devolve o aviso, ou None.

    Caso real: com 1.27 GB livres, o ffmpeg nem chegou a abrir — o Windows
    devolveu "WinError 8: nao ha recursos de memoria suficientes", que ninguem
    liga a "feche o Chrome". O filtro loudnorm tambem ja derrubou um video de um
    lote pelo mesmo motivo. Aviso, nao bloqueio: a estimativa e grosseira e a
    decisao e do usuario.
    """
    livre = ram_livre_mb()
    if livre is None or livre >= RAM_MINIMA_MB:
        return None
    return (f"apenas {livre/1024:.1f} GB de RAM livre (o encode costuma pedir "
            f"~{RAM_MINIMA_MB/1024:.1f} GB).\n"
            "   Feche o navegador e outros programas pesados, ou o ffmpeg pode\n"
            "   nem conseguir iniciar. Confira tambem se sobrou algum auto-editor\n"
            "   de uma execucao interrompida: parar a tarefa mata o terminal mas\n"
            "   deixa o processo filho vivo, segurando a memoria.")


def ganho_para_alvo(medido_lufs: float, alvo: float = ALVO_LUFS) -> float:
    """dB de ganho linear para levar `medido_lufs` ate `alvo`, ja com a margem
    que o limiter vai comer de volta."""
    return round(alvo + MARGEM_LIMITER - medido_lufs, 2)


def medir_loudness(caminho: Path):
    """(loudness_integrado, true_peak) do arquivo, ou (None, None) se falhar.

    Medicao de verdade, no arquivo. Nenhum numero do relatorio pode vir do
    parametro que pedimos ao ffmpeg: num lote real, 18 aulas foram reportadas
    como "-14 LUFS" porque -14 era o que estava no comando, enquanto os arquivos
    estavam entre -17.8 e -27.1. O comando pede; so a medicao sabe.
    """
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(caminho),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    m = re.search(r'\{[^{}]*"input_i"[\s\S]*?\}', (r.stderr or "") + (r.stdout or ""))
    if not m:
        return None, None
    try:
        d = json.loads(m.group(0))
        return float(d["input_i"]), float(d["input_tp"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None, None


def normalizar(entrada: Path, saida: Path, alvo: float = ALVO_LUFS) -> tuple:
    """Ganho linear + limiter de pico. Devolve (lufs, tp) MEDIDOS na saida.

    Devolve (None, None) se falhar, para o chamador decidir. Nunca devolve o
    alvo: o valor volta do arquivo, nao do parametro.
    """
    medido, _ = medir_loudness(entrada)
    if medido is None:
        return None, None
    ganho = ganho_para_alvo(medido, alvo)
    filtro = f"volume={ganho}dB,alimiter=limit={TETO_LINEAR}:level=0"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(entrada), "-af", filtro,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(saida)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 or not saida.exists():
        print(f"ERRO ao normalizar:\n{(r.stderr or r.stdout)[-800:]}")
        return None, None
    return medir_loudness(saida)


def corte_irrelevante(antes_s: float, depois_s: float,
                      piso: float = CORTE_IRRELEVANTE_PCT) -> bool:
    """True se sobrou tao pouco a cortar que o re-encode nao se paga.

    Video ja editado nao tem tempo morto. Num lote real, um arquivo gastou 1h de
    CPU para remover 4 segundos (0.7%) — re-encode disfarcado de corte, com perda
    de qualidade e zero ganho.
    """
    if antes_s <= 0:
        return False
    return (antes_s - depois_s) / antes_s < piso


def corte_suspeito(antes_s: float, depois_s: float,
                   teto: float = CORTE_SUSPEITO_PCT) -> bool:
    """True se sumiu tanta duracao que e bug, nao edicao.

    Fala com pausa normal perde de 10% a 45%. Passou de 70%, o threshold nao
    casou com o nivel da gravacao e o corte comeu a fala — caso real: um video
    de 163s saiu com 2,7s, 98% removido, e so um humano olhando percebeu.
    """
    if antes_s <= 0:
        return False
    return (antes_s - depois_s) / antes_s > teto


def respiros(words: list, base_s: float,
             frase_s: float = RESPIRO_FRASE,
             topico_s: float = RESPIRO_TOPICO,
             pausa_topico: float = PAUSA_TOPICO) -> list:
    """Faixas de silencio a PRESERVAR alem da margem base.

    Devolve [(inicio, fim), ...] para passar ao --add-in do auto-editor. Cada
    faixa cobre a pausa depois de um fim de frase, ate o respiro que aquela
    fronteira merece — e nunca alem do silencio que existe ali.

    A margem base continua cuidando do que acontece dentro da frase; isto so
    devolve ar onde a fala realmente termina um pensamento.
    """
    faixas = []
    for i, p in enumerate(words[:-1]):
        if not p["word"].strip().rstrip('"\')').endswith(tuple(FIM_DE_FRASE)):
            continue
        vao = words[i + 1]["start"] - p["end"]
        if vao <= base_s:
            continue                       # a margem base ja cobre essa pausa
        alvo = topico_s if vao >= pausa_topico else frase_s
        guardar = min(alvo, vao)
        if guardar > base_s:
            faixas.append((round(p["end"], 2), round(p["end"] + guardar, 2)))
    return faixas


def curva_rms(video: Path, passo_s: float = PASSO_RMS_S) -> list:
    """Energia (RMS) do audio, uma amostra a cada `passo_s`. [] se falhar.

    So stdlib: ffmpeg decodifica para wav mono 8kHz e o resto e `wave` + `array`.
    8kHz basta de sobra — estamos procurando onde a fala PARA, nao timbre.
    """
    import array
    import math
    import wave

    tmp = Path(tempfile.gettempdir()) / "remove-fillers"
    tmp.mkdir(parents=True, exist_ok=True)
    w = tmp / f"{slugify(video.stem)}_rms.wav"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "8000", "-f", "wav", str(w)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 or not w.exists():
        return []
    try:
        with wave.open(str(w), "rb") as f:
            if f.getsampwidth() != 2:
                return []
            taxa = f.getframerate()
            bruto = f.readframes(f.getnframes())
    finally:
        w.unlink(missing_ok=True)

    amostras = array.array("h")
    amostras.frombytes(bruto[:len(bruto) - (len(bruto) % 2)])
    salto = max(1, int(taxa * passo_s))
    curva = []
    for k in range(0, len(amostras), salto):
        bloco = amostras[k:k + salto]
        if not bloco:
            break
        curva.append(math.sqrt(sum(x * x for x in bloco) / len(bloco)))
    return curva


def encaixar_no_vale(curva: list, t: float, passo_s: float = PASSO_RMS_S,
                     janela_s: float = JANELA_SNAP_S) -> float:
    """Desliza `t` ate o ponto de menor energia dentro de +-`janela_s`.

    Sem curva (ffmpeg falhou), devolve `t` intacto: encaixar e melhoria, nao
    requisito — a skill continua cortando sem ele.
    """
    if not curva:
        return round(t, 3)
    centro = int(t / passo_s)
    raio = max(1, int(janela_s / passo_s))
    a, b = max(0, centro - raio), min(len(curva), centro + raio + 1)
    if a >= b:
        return round(t, 3)
    melhor = min(range(a, b), key=lambda k: curva[k])
    return round(melhor * passo_s, 3)


def faixa_palavra(words: list, i: int, pad: float = PAD_CORTE_S) -> tuple:
    """(inicio, fim) para cortar a palavra i, com folga ate o silencio vizinho.

    Cortar exatamente [start, end] deixa fragmento audivel em palavra curta. Caso
    real: um "ok?" de 0.16s — a 60fps sao ~10 quadros, e o auto-editor corta em
    limite de quadro, entao qualquer desvio de fronteira sobra pedaco.

    A folga so avanca sobre SILENCIO: no maximo metade do intervalo ate o vizinho
    de cada lado, nunca encostando na palavra ao lado.
    """
    ini, fim = words[i]["start"], words[i]["end"]
    if i > 0:
        ini -= min(pad, max(0.0, (ini - words[i - 1]["end"]) / 2))
    if i + 1 < len(words):
        fim += min(pad, max(0.0, (words[i + 1]["start"] - fim) / 2))
    return round(ini, 2), round(fim, 2)


def estimar_custo(duracao_s: float, modelo: str = STT_MODEL):
    """$ estimado da transcricao. None se o modelo nao esta na tabela."""
    preco = PRECO_MIN.get(modelo)
    return None if preco is None else (duracao_s / 60.0) * preco


def _fmt_custo(v) -> str:
    return "?" if v is None else (f"${v:.4f}" if v < 0.01 else f"${v:.2f}")


# ── transcricao via OpenRouter ────────────────────────────────────────────────

def transcrever(video: Path, modelo: str = STT_MODEL) -> list:
    import base64
    import urllib.request

    carregar_env()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY nao encontrada.\n\n"
            "O modo --fillers precisa de uma chave da OpenRouter para transcrever.\n"
            "Pegue a sua em: https://openrouter.ai/keys\n\n"
            "  Windows (PowerShell), permanente:\n"
            '    [Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", "sk-or-...", "User")\n'
            "    (feche e abra o terminal depois)\n\n"
            "  macOS / Linux:\n"
            '    export OPENROUTER_API_KEY="sk-or-..."\n\n'
            "O corte de silencio e a normalizacao NAO precisam de chave:\n"
            "rode a skill sem --fillers que funciona de graca e offline."
        )

    tmp = Path(tempfile.gettempdir()) / "remove-fillers"
    tmp.mkdir(parents=True, exist_ok=True)
    audio = tmp / f"{slugify(video.stem)}_fillers.mp3"
    print("🎵 extraindo audio...", flush=True)
    extract_audio(video, audio)

    total = get_duration(audio)
    custo = estimar_custo(total, modelo)
    print(f"💰 {total/60:.1f} min de audio · {modelo} · "
          f"custo estimado {_fmt_custo(custo)}", flush=True)

    def _post(b64: str) -> dict:
        payload = {
            "model": modelo,
            "input_audio": {"data": b64, "format": "mp3"},
            "language": "pt",
            "response_format": "verbose_json",
            "timestamp_granularities": ["word"],
        }
        req = urllib.request.Request(
            f"{OPENROUTER}/audio/transcriptions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)

    mb = audio.stat().st_size / 1_048_576
    words = []
    if mb <= MAX_MB:
        print(f"🎧 transcrevendo ({mb:.1f} MB)...", flush=True)
        words = _post(base64.b64encode(audio.read_bytes()).decode()).get("words") or []
    else:
        passo = CHUNK_MINUTES * 60
        n = -(-int(total) // int(passo))
        print(f"🎧 transcrevendo em {n} partes ({mb:.1f} MB)...", flush=True)
        for i in range(n):
            parte = tmp / f"fillers_chunk_{i}.mp3"
            ini = i * passo
            extract_chunk(audio, parte, ini, min(passo, total - ini))
            print(f"   parte {i+1}/{n}...", flush=True)
            for w in (_post(base64.b64encode(parte.read_bytes()).decode()).get("words") or []):
                words.append({"word": w["word"], "start": w["start"] + ini, "end": w["end"] + ini})
            parte.unlink(missing_ok=True)

    audio.unlink(missing_ok=True)
    return words


# ── autoteste ─────────────────────────────────────────────────────────────────



# ── autoteste ─────────────────────────────────────────────────────────────────
#
# So sobrou o que e genuinamente mecanico. Cada caso abaixo veio de um bug real
# e carrega os numeros dele, para ninguem afrouxar um limite sem o teste cair.

def autoteste():
    w = lambda t, s, e: {"word": t, "start": s, "end": e}

    # ── encaixe no vale ──────────────────────────────────────────────────────
    # curva de 1s a cada 0.01s, fala alta com um vale em 0.50s
    vale = [100.0] * 100
    vale[50] = 1.0
    assert encaixar_no_vale(vale, 0.47) == 0.50, encaixar_no_vale(vale, 0.47)
    assert encaixar_no_vale(vale, 0.55) == 0.50
    assert encaixar_no_vale(vale, 0.90) != 0.50    # fora do alcance de 0.15s
    assert encaixar_no_vale([], 1.234) == 1.234    # sem curva, tempo intacto
    assert isinstance(encaixar_no_vale(vale, 99.0), float)   # alem do fim, sem estourar

    dois = [100.0] * 100
    dois[48] = 30.0
    dois[52] = 2.0
    assert encaixar_no_vale(dois, 0.50) == 0.52, encaixar_no_vale(dois, 0.50)

    # ── folga no corte de palavra ────────────────────────────────────────────
    # tempos reais do "ok?" de 0.16s que sobrou pela metade. Atras ele esta
    # colado em "ativos" (silencio zero), entao nao avanca. Na frente ha 0.24s;
    # metade seria 0.12, mas o teto de 0.06 e menor e vence.
    tres = [w("ativos", 0.0, 0.64), w("ok", 0.64, 0.80), w("e", 1.04, 1.37)]
    ini, fim = faixa_palavra(tres, 1)
    assert ini == 0.64, ini
    assert abs(fim - 0.86) < 0.011, fim
    assert fim < tres[2]["start"], "a folga encostou na palavra seguinte"

    # silencio apertado: metade do intervalo (0.02) vence o teto
    apertado = [w("a", 0.0, 0.50), w("ok", 0.50, 0.66), w("b", 0.70, 1.00)]
    _, fim = faixa_palavra(apertado, 1)
    assert abs(fim - 0.68) < 0.011, fim
    assert fim < apertado[2]["start"]

    # ── respiro variavel ─────────────────────────────────────────────────────
    meio = [w("vou", 0.0, 0.3), w("falar", 0.5, 0.9), w("sobre", 1.6, 2.0)]
    assert respiros(meio, 0.1) == [], respiros(meio, 0.1)   # sem pontuacao, sem respiro

    frase = [w("coisas.", 0.0, 0.3), w("Primeiro", 0.5, 0.9)]
    assert respiros(frase, 0.1) == [(0.3, 0.5)], respiros(frase, 0.1)  # guarda o que existe

    folga = [w("coisas.", 0.0, 0.3), w("Primeiro", 0.75, 1.15)]
    assert respiros(folga, 0.1) == [(0.3, 0.65)], respiros(folga, 0.1)  # guarda 0.35, nao tudo
    assert folga[1]["start"] - folga[0]["end"] < PAUSA_TOPICO

    topico = [w("entender.", 0.0, 0.3), w("Agora", 1.4, 1.8)]
    assert respiros(topico, 0.1) == [(0.3, 0.9)], respiros(topico, 0.1)  # virada: 0.60

    curta = [w("coisas.", 0.0, 0.3), w("Primeiro", 0.35, 0.7)]
    assert respiros(curta, 0.1) == [], respiros(curta, 0.1)  # a margem base ja cobre

    for fim_frase, esperado in [("agora?", 1), ("agora!", 1), ("agora,", 0), ("agora", 0)]:
        t = [w(fim_frase, 0.0, 0.3), w("Talvez", 1.5, 1.9)]
        assert len(respiros(t, 0.1)) == esperado, (fim_frase, respiros(t, 0.1))

    # respiro dentro de um corte e contradicao (--add-in vs --cut-out).
    # Reproduz a regra que aplicar() usa, para ela nao se perder num refactor.
    cortes_t = [(10.0, 12.0), (20.0, 21.0)]
    ar_t = [(5.0, 5.4), (11.0, 11.4), (9.8, 10.2), (15.0, 15.4), (20.5, 22.0)]
    sobrevivem = [(a, b) for a, b in ar_t
                  if not any(a < cb and b > ca for ca, cb in cortes_t)]
    assert sobrevivem == [(5.0, 5.4), (15.0, 15.4)], sobrevivem

    # ── RAM ──────────────────────────────────────────────────────────────────
    # medir nunca pode quebrar o corte; nao sabendo medir, segue sem avisar
    livre = ram_livre_mb()
    assert livre is None or livre > 0, livre
    assert aviso_de_ram() is None or isinstance(aviso_de_ram(), str)

    # ── ganho para o alvo ────────────────────────────────────────────────────
    # o 001 do lote real estava a -44.4 LUFS, alvo -14: ~30 dB mais a margem
    assert ganho_para_alvo(-44.4) == 30.9, ganho_para_alvo(-44.4)
    assert ganho_para_alvo(-14.0) == 0.5
    assert ganho_para_alvo(-10.0) == -3.5          # fonte alta tambem desce

    # ── guardrails de corte ──────────────────────────────────────────────────
    # o caso real de 163s -> 2.7s tem que disparar
    assert corte_suspeito(163.0, 2.7)
    assert corte_suspeito(307.0, 7.0)
    assert not corte_suspeito(318.0, 156.0)        # 51%, agressivo mas plausivel
    assert not corte_suspeito(69.4, 37.4)          # teste real do usuario, 46%
    assert not corte_suspeito(100.0, 100.0)
    assert not corte_suspeito(0.0, 0.0)            # divisao por zero nao quebra

    # o "04 - COMO GERAR FOTOS": 1h de CPU para tirar 0.7%
    assert corte_irrelevante(3600.0, 3575.0)
    assert not corte_irrelevante(163.0, 142.4)     # 12.6%, corte normal
    assert not corte_irrelevante(0.0, 0.0)

    # ── .env ─────────────────────────────────────────────────────────────────
    env = Path(tempfile.mkdtemp(prefix="remove-fillers-teste-")) / ".env"
    env.write_text("# comentario\nSENHA_DO_BANCO=nao-me-leia\n"
                   "OPENROUTER_API_KEY=sk-teste\n", encoding="utf-8")
    assert _chave_no_env(env) == "sk-teste", _chave_no_env(env)

    env.write_text('OPENROUTER_API_KEY="sk-com-aspas"\n', encoding="utf-8")
    assert _chave_no_env(env) == "sk-com-aspas"

    env.write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
    assert _chave_no_env(env) is None              # .env.example nao conta

    env.write_text("SENHA_DO_BANCO=nao-me-leia\n", encoding="utf-8")
    assert _chave_no_env(env) is None

    # BOM: o que Bloco de Notas e `Out-File -Encoding utf8` gravam no Windows
    env.write_text("OPENROUTER_API_KEY=sk-com-bom\n", encoding="utf-8-sig")
    assert env.read_bytes().startswith(b"\xef\xbb\xbf"), "o teste precisa do BOM"
    assert _chave_no_env(env) == "sk-com-bom", _chave_no_env(env)
    shutil.rmtree(env.parent, ignore_errors=True)

    print("✅ autoteste passou")


# ── aplicar ───────────────────────────────────────────────────────────────────

def aplicar(video: Path, dados: Path, saida: Path, margin: str = "0.2s"):
    """Corta silencio + cortes aprovados num passe so e normaliza o audio.

    O --cut-out do auto-editor 29.x aceita UMA faixa por ocorrencia, apesar do
    help anunciar `[START,STOP ...]`. Passar varias de uma vez faz ele tratar a
    ultima como arquivo de entrada ("Could not open input file: 432.42sec,...").
    Por isso a flag e repetida uma vez por faixa.
    """
    info = json.loads(dados.read_text(encoding="utf-8"))
    cortes = info["cortes"]
    if not cortes:
        print("Nada a cortar: o JSON nao tem faixas.")
        sys.exit(1)

    print("📊 medindo energia do audio para encaixar os cortes...", flush=True)
    curva = curva_rms(video)
    if curva:
        movidos = 0
        encaixados = []
        for a, b in cortes:
            na, nb = encaixar_no_vale(curva, a), encaixar_no_vale(curva, b)
            if nb <= na:                      # encaixe degenerou: fica o original
                na, nb = a, b
            movidos += (abs(na - a) > 0.005) + (abs(nb - b) > 0.005)
            encaixados.append((na, nb))
        cortes = encaixados
        print(f"   {movidos} de {len(cortes)*2} fronteiras deslizadas para o vale")
    else:
        print("   ⚠️  nao consegui medir a energia; cortando nas fronteiras do ASR")

    faixas = []
    for a, b in cortes:
        faixas += ["--cut-out", f"{a:.2f}sec,{b:.2f}sec"]

    # respiros vem prontos no JSON (quem tem a transcricao e quem os calcula).
    # --add-in preserva a faixa, entao a margem base pode ser apertada sem
    # colar as frases umas nas outras.
    #
    # Respiro que cai dentro de um corte aprovado e contradicao: --add-in manda
    # guardar o que --cut-out manda tirar. O corte ganha, e o filtro fica AQUI
    # e nao no chamador — quem monta o JSON nao deve precisar saber disso.
    ar = [(a, b) for a, b in (info.get("respiros") or [])
          if not any(a < cb and b > ca for ca, cb in cortes)]
    for a, b in ar:
        faixas += ["--add-in", f"{a:.2f}sec,{b:.2f}sec"]
    if ar:
        print(f"🌬️  {len(ar)} respiro(s) preservados nas viradas de frase", flush=True)

    tmp_dir = saida.parent / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cache = tmp_dir / f"cache_{slugify(video.stem)}"
    pre = tmp_dir / f"{slugify(video.stem)}_pre.mp4"
    corte = tmp_dir / f"{slugify(video.stem)}_corte.mp4"

    # NORMALIZAR ANTES DE CORTAR. O threshold do auto-editor e absoluto (4% do
    # fundo de escala, ~-28dB), nao relativo ao pico do arquivo. Numa gravacao
    # baixa — caso real: mean -48dB, pico -22dB — a fala inteira fica ABAIXO do
    # limiar e o corte destroi o video: 163s viraram 2,7s. Normalizando primeiro,
    # toda entrada chega no mesmo nivel e o limiar volta a significar algo (nesse
    # mesmo arquivo, os quadros acima do limiar foram de 0,8% para 81,5%).
    # Custa duas passagens de audio; o encode de video continua sendo um so,
    # porque ffmpeg-normalize copia o video (-c:v copy).
    aviso = aviso_de_ram()
    if aviso:
        print(f"⚠️  {aviso}", flush=True)

    print("🔊 nivelando audio antes de cortar...", flush=True)
    lufs_pre, _ = normalizar(video, pre)
    if lufs_pre is None:
        sys.exit(1)
    print(f"   entrada nivelada: {lufs_pre:.1f} LUFS", flush=True)

    print(f"✂️  cortando silencio + {len(faixas)//2} trecho(s) (margin {margin})...", flush=True)
    r = subprocess.run(
        ["auto-editor", str(pre), "--edit", "audio:threshold=4%", "--margin", margin,
         *faixas, "--temp-dir", str(cache), "-o", str(corte), "--no-open"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    pre.unlink(missing_ok=True)
    shutil.rmtree(cache, ignore_errors=True)
    if r.returncode != 0 or not corte.exists():
        print(f"ERRO no auto-editor:\n{(r.stderr or r.stdout)[-800:]}")
        sys.exit(1)

    print(f"🔊 normalizando audio (alvo {ALVO_LUFS:.0f} LUFS)...", flush=True)
    lufs, tp = normalizar(corte, saida)
    if lufs is None:
        sys.exit(1)
    corte.unlink(missing_ok=True)
    try:
        tmp_dir.rmdir()
    except OSError:
        pass

    antes = get_duration(video)
    depois = get_duration(saida)
    pct = (antes - depois) / antes * 100 if antes else 0

    # o loudness sai MEDIDO no arquivo entregue, nunca copiado do parametro
    desvio = abs(lufs - ALVO_LUFS)
    marca = "" if desvio <= TOLERANCIA_LU else f"  ⚠️  {desvio:.1f} LU fora do alvo"
    print(f"   audio medido: {lufs:.1f} LUFS · pico {tp:.1f} dBTP{marca}")
    if desvio > TOLERANCIA_LU:
        print("   A fonte nao alcancou o alvo mesmo com limiter. Costuma ser\n"
              "   gravacao muito baixa com pico alto (clique de mouse, teclado).")

    if corte_irrelevante(antes, depois):
        print(f"\n⚠️  CORTE IRRELEVANTE: so {pct:.1f}% removido "
              f"({antes - depois:.1f}s de {antes/60:.1f} min).\n"
              "   Esse video provavelmente ja foi editado e nao tem tempo morto.\n"
              "   O re-encode custou qualidade e nao entregou ganho. Considere\n"
              f"   usar o original.\n   Arquivo gerado mesmo assim: {saida}")
        return

    if corte_suspeito(antes, depois):
        print(f"\n⚠️  CORTE SUSPEITO: {antes/60:.1f} min viraram {depois/60:.1f} min "
              f"({pct:.0f}% removido).\n"
              "   Isso nao e pausa, e fala sendo cortada. Quase sempre o threshold\n"
              "   nao casou com o nivel da gravacao. Confira o arquivo ANTES de usar,\n"
              "   e se estiver destruido rode de novo com um threshold menor:\n"
              '     --edit "audio:threshold=2%"\n'
              f"   Arquivo gerado mesmo assim: {saida}")
        return

    print(f"\n✅ {saida}\n   {antes/60:.1f} min → {depois/60:.1f} min ({pct:.0f}% removido)")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if "--autoteste" in args:
        autoteste()
        return

    margin = "0.2s"
    if "--margin" in args:
        i = args.index("--margin")
        if i + 1 >= len(args):
            print("Uso: --margin <duracao>, por exemplo --margin 0.0s")
            sys.exit(1)
        margin = args[i + 1]
        del args[i:i + 2]

    modelo = STT_MODEL
    if "--modelo" in args:
        i = args.index("--modelo")
        if i + 1 >= len(args):
            print("Uso: --modelo <id>, por exemplo --modelo microsoft/mai-transcribe-2")
            sys.exit(1)
        modelo = args[i + 1]
        del args[i:i + 2]

    if "--aplicar" in args:
        resto = [a for a in args if a != "--aplicar"]
        if len(resto) != 3:
            print("Uso: --aplicar <video.mp4> <cortes.json> <saida.mp4> [--margin 0.2s]")
            sys.exit(1)
        video, dados, saida = (Path(x) for x in resto)
        for p in (video, dados):
            if not p.exists():
                print(f"Erro: arquivo nao encontrado: {p}")
                sys.exit(1)
        aplicar(video, dados, saida, margin)
        return

    if not args:
        print(__doc__)
        sys.exit(1)

    video = Path(args[0])
    if not video.exists():
        print(f"Erro: arquivo nao encontrado: {video}")
        sys.exit(1)

    saida = Path(args[args.index("--json") + 1]) if "--json" in args else \
        video.with_suffix(".fillers.json")

    # falta de chave e erro de configuracao do usuario, nao bug: mostra a
    # mensagem limpa em vez de um traceback, que assusta quem nao programa
    try:
        words = transcrever(video, modelo)
    except RuntimeError as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    if not words:
        print(f"\n❌ O modelo {modelo} nao devolveu timestamp por palavra.\n\n"
              "Nem todo modelo do OpenRouter suporta `timestamp_granularities:\n"
              "[\"word\"]` — alguns ignoram e outros devolvem 400. Tente outro:\n\n"
              "  --modelo microsoft/mai-transcribe-2      ($0.10/hora, word ok)\n"
              "  --modelo openai/whisper-large-v3-turbo   (barato, timestamp aproximado)\n")
        sys.exit(1)

    dur = words[-1]["end"]

    # Medicao, e so medicao. `gap_antes` e o silencio antes da palavra: quem
    # recomeca para antes de recomecar, e essa pausa some numa transcricao em
    # texto corrido. `conf` denuncia palavra truncada no meio da silaba, que
    # volta como fragmento sem sentido e com confianca baixa.
    saida_words = []
    anterior_fim = 0.0
    baixa_conf = []
    for i, x in enumerate(words):
        item = {"i": i, "word": x["word"].strip(),
                "start": round(x["start"], 2), "end": round(x["end"], 2),
                "gap_antes": round(max(0.0, x["start"] - anterior_fim), 2)}
        c = x.get("confidence")
        if c is not None:
            item["conf"] = round(float(c), 3)
            if float(c) < 0.5:
                baixa_conf.append(i)
        saida_words.append(item)
        anterior_fim = x["end"]

    pausas = sum(1 for x in saida_words if x["gap_antes"] >= 0.35)

    dados = {
        "modelo_stt": modelo,
        "custo_estimado_usd": round(estimar_custo(dur, modelo) or 0, 4),
        "palavras": len(words),
        "duracao_s": round(dur, 2),
        "words": saida_words,
    }
    saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*72}")
    print(f"  {len(words)} palavras · {dur/60:.1f} min de fala · {modelo}")
    print(f"  custo da transcricao: {_fmt_custo(estimar_custo(dur, modelo))}")
    print(f"{'='*72}")
    print(f"  {pausas} pausa(s) de 0.35s ou mais — candidatas a inicio de take nova")
    if baixa_conf:
        print(f"  {len(baixa_conf)} palavra(s) com confianca abaixo de 0.5 — "
              "veja se sao fragmento truncado")
    elif not any("conf" in x for x in saida_words):
        print("  (este modelo nao devolveu confianca por palavra)")
    print(f"{'='*72}")
    print(f"\n💾 {saida}")
    print("\nNada foi julgado aqui. Quem le este JSON, corrige a transcricao e")
    print("decide os cortes e o agente, seguindo o passo 5b do SKILL.md.")


if __name__ == "__main__":
    main()
