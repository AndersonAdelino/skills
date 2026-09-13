#!/usr/bin/env python3
"""
remove-fillers.py — transcreve com timestamp por palavra e acha candidatos a corte

Script da skill /cut-silence (modo --fillers).

DIVISAO DE TRABALHO. Este script NAO julga o que e vicio de linguagem. Ele faz
so o que precisa de API ou de heuristica deterministica:

  1. extrai audio e transcreve com timestamp por palavra
  2. acha candidatos mecanicos: gagueira (palavra colada repetida) e duplicata
     (take abandonada, o locutor refez o trecho do inicio)
  3. escreve tudo num JSON

Quem le esse JSON, corrige a transcricao, decide os vicios de linguagem e monta
o relatorio e o agente (Claude Code), seguindo o passo a passo do SKILL.md. Julgar
no agente sai mais barato, nao depende de acertar um prompt para um modelo remoto,
funciona em qualquer idioma e deixa voce discordar de um corte na conversa em vez
de editar JSON na mao.

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

import difflib
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

# guardrails locais
MAX_SEQUENCIA    = 6        # nunca remover mais de 6 palavras seguidas
GAP_GAGUEIRA     = 0.6      # repeticao dentro desse intervalo = gagueira, nao enfase

# ── duplicata (recomeco de take) ──────────────────────────────────────────────
# Gagueira e palavra colada repetida ("hoje hoje eu vou"). Duplicata e outra
# coisa: o locutor percebe que errou, para, e refaz o trecho inteiro do comeco
# ("Fala pessoal! ... Olá pessoal! Anderson aqui"). O corte certo vai do inicio
# da take ruim ate o inicio da take boa.
#
# A busca abaixo e PERMISSIVA de proposito (recall): "fala pessoal" e "ola
# pessoal" so coincidem numa palavra, entao um limiar apertado perderia justo o
# caso que importa. A precisao vem depois, do agente confirmando candidato a
# candidato com o texto na frente.
JANELA_DUPLICATA   = 90.0   # ate onde olhar para tras, em segundos
MIN_CHARS_SONDA    = 6      # sonda curta casa por acaso; exigido nos DOIS lados
LIMIAR_DUPLICATA   = 0.78   # similaridade de caractere (SequenceMatcher)
MAX_DUPLICATA_S    = 15.0   # take abandonada maior que isso nao e recomeco
PAUSA_RECOMECO     = 0.35   # so palavra precedida de pausa comeca take nova

# TAMANHO DE SONDA NAO PODE SER FIXO. Os dois casos reais pedem opostos:
#
#   "fala pessoal"  -> "ola pessoal"      so 1 palavra em comum: precisa sonda CURTA
#   "Ok, parece..." -> "Certo, parece..." 1a palavra difere:     precisa sonda LONGA
#
# Com 2 palavras o segundo da 0.737 e passa batido; com 6 da 0.902. Com 6 o
# primeiro nunca casa. Entao testamos varios tamanhos em cada ponto de recomeco
# e ficamos com o melhor. Uma sonda curta demais em caracteres simplesmente nao
# desqualifica as maiores — era essa trava que engolia recomeco comecando em
# palavra funcional ("O que...", 4 chars).
SONDAS_DUPLICATA = (2, 3, 4, 6)

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
# o recurso ("fala pessoal" -> "ola pessoal") da 0.857 em 2,5s.

# Palavras que nao podem sair por palpite de vicio, por mais convencido que o
# juiz esteja. Vocativo: quem grava uma aula fala com a audiencia o tempo todo
# ("era isso, pessoal"). Pronome: tirar o sujeito quebra a frase ("o que ele
# corrigiu" -> "o que corrigiu"), erro real observado em teste.
# Gagueira e duplicata sao isentas: a palavra sobrevive na outra ocorrencia.
PROTEGIDO = {
    "pessoal", "galera", "cara", "gente", "vocês", "voces", "você", "voce",
    "eu", "ele", "ela", "eles", "elas", "nós", "nos",
    "meu", "minha", "seu", "sua", "dele", "dela",
}


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


def estimar_custo(duracao_s: float, modelo: str = STT_MODEL):
    """$ estimado da transcricao. None se o modelo nao esta na tabela."""
    preco = PRECO_MIN.get(modelo)
    return None if preco is None else (duracao_s / 60.0) * preco


def _fmt_custo(v) -> str:
    return "?" if v is None else (f"${v:.4f}" if v < 0.01 else f"${v:.2f}")


# ── deteccao de gagueira (heuristica pura) ───────────────────────────────────

def achar_gagueiras(words: list) -> list:
    """Palavra repetida imediatamente e colada = gagueira. Devolve indices a remover.

    Numa repeticao 'eu eu eu acho', mantem a ULTIMA ocorrencia (a que emenda na
    frase) e remove as anteriores.
    """
    remover = []
    i = 0
    while i < len(words):
        j = i
        while (j + 1 < len(words)
               and _norm(words[j]["word"]) == _norm(words[i]["word"])
               and _norm(words[i]["word"])
               and words[j + 1]["start"] - words[j]["end"] < GAP_GAGUEIRA
               and _norm(words[j + 1]["word"]) == _norm(words[i]["word"])):
            j += 1
        if j > i:
            remover.extend(range(i, j))   # tudo menos a ultima
        i = j + 1
    return remover


# ── deteccao de duplicata / recomeco de take ─────────────────────────────────

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


def _texto(words: list, ini: int, fim: int) -> str:
    """Texto normalizado e colado de words[ini:fim], para comparar."""
    return "".join(_norm(w["word"]) for w in words[ini:fim])


def achar_duplicatas(words: list,
                     janela_s: float = JANELA_DUPLICATA,
                     sondas: tuple = SONDAS_DUPLICATA,
                     limiar: float = LIMIAR_DUPLICATA,
                     max_span_s: float = MAX_DUPLICATA_S,
                     pausa_min: float = PAUSA_RECOMECO) -> list:
    """Acha take abandonada: o locutor comeca, erra, para, e refaz do inicio.

    Parte das PAUSAS, nao do texto. Quem recomeca para antes de recomecar, entao
    so palavra precedida de pausa e candidata a inicio de take nova. Para cada
    uma, olha para tras procurando o comeco parecido que ela esta refazendo.

    Buscar pelo texto primeiro nao funciona: em "fala pessoal ... ola pessoal"
    as duas versoes so compartilham UMA palavra, e qualquer sonda maior afunda a
    similaridade. Ancorar na pausa deixa a sonda ser curta sem encher de falso
    positivo, porque so os pontos de recomeco sao testados.

    Achando o par (i, j), a take ruim e words[i:j] inteira. Fica a ultima versao,
    que e a corrigida — o mesmo corte que um editor humano faria.

    Devolve [{ini, fim, eco, score, dur_s}, ...] com `fim` inclusivo.
    Candidatos, nao veredito: quem confirma e o agente, lendo o texto.
    """
    n = len(words)
    achados = []
    ultimo_fim = -1
    menor = min(sondas)
    for j in range(1, n - menor + 1):
        if j <= ultimo_fim:                         # ja dentro de um corte achado
            continue
        if words[j]["start"] - words[j - 1]["end"] < pausa_min:
            continue                                # sem pausa, nao e recomeco
        melhor = None
        for tam in sondas:
            if j + tam > n:
                continue
            sonda = _texto(words, j, j + tam)
            if len(sonda) < MIN_CHARS_SONDA:
                continue                            # este tamanho nao serve; os outros ainda podem
            for i in range(j - tam, -1, -1):
                if words[j]["start"] - words[i]["start"] > janela_s:
                    break                           # saiu da janela, para de olhar
                # o lado de tras tambem precisa de corpo: foi um alvo de 5 chars
                # ("ecada") que gerou o falso positivo de 36s no primeiro teste real
                alvo = _texto(words, i, i + tam)
                if len(alvo) < MIN_CHARS_SONDA:
                    continue
                r = difflib.SequenceMatcher(None, sonda, alvo).ratio()
                if r >= limiar and (melhor is None or r > melhor[1]):
                    melhor = (i, r)
        if melhor:
            i, r = melhor
            # Dois pontos de recomeco podem casar com a MESMA origem (o texto se
            # repete tres vezes), e aí as duas faixas se sobrepoem. Sobreposicao
            # vira corte maior do que qualquer uma das duas propunha, entao a
            # segunda e descartada.
            if i < ultimo_fim:
                continue
            dur = words[j]["start"] - words[i]["start"]
            if dur <= max_span_s:
                achados.append({"ini": i, "fim": j - 1, "eco": j,
                                "score": round(r, 2), "dur_s": round(dur, 2)})
                ultimo_fim = j
    return achados


# ── juncao de indices em faixas de tempo ──────────────────────────────────────

def indices_para_faixas(words: list, indices: list) -> list:
    """Agrupa indices consecutivos e devolve [(inicio_s, fim_s), ...]."""
    if not indices:
        return []
    idx = sorted(set(indices))
    faixas, ini = [], idx[0]
    ant = idx[0]
    for k in idx[1:]:
        if k != ant + 1:
            faixas.append((words[ini]["start"], words[ant]["end"]))
            ini = k
        ant = k
    faixas.append((words[ini]["start"], words[ant]["end"]))
    return faixas


def validar(words: list, indices: list, gagueiras: set = frozenset(),
            duplicatas: set = frozenset()) -> tuple:
    """Devolve (indices_limpos, avisos). Descarta o que viola guardrail.

    `gagueiras` e `duplicatas` sao isentas de PROTEGIDO, e duplicata tambem de
    MAX_SEQUENCIA: um recomeco e longo por definicao, e cada palavra dele
    reaparece na take boa logo em seguida. O limite de 6 existe para conter
    palpite de vicio, onde bloco longo e sinal de julgamento errado.
    """
    avisos = []
    n = len(words)
    limpos = sorted({i for i in indices if isinstance(i, int) and 0 <= i < n})
    isentos = set(duplicatas)

    descartados = len(set(indices)) - len(limpos)
    if descartados > 0:
        avisos.append(f"{descartados} indice(s) fora da faixa 0..{n-1}, descartados")

    fora = []
    seq = []
    for i in [x for x in limpos if x not in isentos] + [None]:
        if seq and (i is None or i != seq[-1] + 1):
            if len(seq) > MAX_SEQUENCIA:
                fora.extend(seq)
            seq = []
        if i is not None:
            seq.append(i)
    if fora:
        avisos.append(f"{len(fora)} palavra(s) em bloco maior que {MAX_SEQUENCIA} seguidas, descartadas")
        limpos = [i for i in limpos if i not in set(fora)]

    prot = [i for i in limpos
            if i not in gagueiras and i not in isentos
            and _norm(words[i]["word"]) in PROTEGIDO]
    if prot:
        amostra = ", ".join(sorted({words[i]["word"].strip() for i in prot})[:5])
        avisos.append(f"{len(prot)} palavra(s) protegida(s) recusada(s) ({amostra})")
        limpos = [i for i in limpos if i not in set(prot)]

    return limpos, avisos


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


# ── contexto para o relatorio ────────────────────────────────────────────────

def contexto(words: list, i: int, janela: int = 4) -> str:
    ini, fim = max(0, i - janela), min(len(words), i + janela + 1)
    return " ".join(
        (f"[{w['word'].strip()}]" if k == i else w["word"].strip())
        for k, w in enumerate(words[ini:fim], start=ini)
    )


# ── autoteste ─────────────────────────────────────────────────────────────────

def autoteste():
    w = lambda t, s, e: {"word": t, "start": s, "end": e}

    # gagueira: mantem a ultima repeticao
    words = [w("eu", 0.0, 0.2), w("eu", 0.25, 0.45), w("eu", 0.5, 0.7), w("acho", 0.75, 1.1)]
    assert achar_gagueiras(words) == [0, 1], achar_gagueiras(words)

    # pausa longa entre iguais nao e gagueira, e enfase
    words = [w("muito", 0.0, 0.3), w("muito", 2.0, 2.3)]
    assert achar_gagueiras(words) == [], achar_gagueiras(words)

    # palavras diferentes nao viram gagueira
    words = [w("o", 0.0, 0.1), w("problema", 0.15, 0.6)]
    assert achar_gagueiras(words) == []

    # faixas: indices consecutivos viram uma faixa so
    words = [w("a", 0, 1), w("b", 1, 2), w("c", 2, 3), w("d", 5, 6)]
    assert indices_para_faixas(words, [0, 1, 3]) == [(0, 2), (5, 6)]
    assert indices_para_faixas(words, []) == []

    # guardrail: indice fora da faixa cai fora
    limpos, avisos = validar(words, [0, 99, -3])
    assert limpos == [0] and any("fora da faixa" in a for a in avisos), (limpos, avisos)

    # guardrail: bloco longo demais e recusado
    muitos = [w(str(i), i, i + 0.5) for i in range(20)]
    limpos, avisos = validar(muitos, list(range(0, MAX_SEQUENCIA + 2)))
    assert limpos == [], (limpos, avisos)

    # ...mas duplicata e isenta: recomeco de take e longo por natureza
    dup = set(range(0, MAX_SEQUENCIA + 2))
    limpos, _ = validar(muitos, list(dup), duplicatas=dup)
    assert limpos == sorted(dup), limpos

    # guardrail: vocativo protegido
    voc = [w("obrigado", 0, 1), w("pessoal", 1, 2)]
    limpos, avisos = validar(voc, [1])
    assert limpos == [] and any("protegida" in a for a in avisos), (limpos, avisos)

    # guardrail: pronome protegido — o erro real observado ("o que [ele] corrigiu")
    pron = [w("que", 0, 1), w("ele", 1, 2), w("corrigiu", 2, 3)]
    assert validar(pron, [1])[0] == []

    # ...mas gagueira e isenta, senao a protecao de pronome mataria o recurso
    gag = [w("eu", 0.0, 0.2), w("eu", 0.25, 0.45), w("eu", 0.5, 0.7), w("acho", 0.75, 1.1)]
    idx = achar_gagueiras(gag)
    assert validar(gag, idx, gagueiras=set(idx))[0] == [0, 1], validar(gag, idx, set(idx))

    # duplicata: take abandonada e refeita. O caso real que motivou o recurso —
    # "Fala pessoal" e "Ola pessoal" so coincidem numa palavra. A pausa de 0.8s
    # antes de "ola" e o que marca o recomeco, como na fala de verdade.
    dup_words = []
    for k, t in enumerate(["fala", "pessoal", "hoje", "eu", "vou", "falar"]):
        dup_words.append(w(t, k * 0.5, k * 0.5 + 0.4))
    base = 5 * 0.5 + 0.4 + 0.8
    for k, t in enumerate(["ola", "pessoal", "anderson", "aqui"]):
        dup_words.append(w(t, base + k * 0.5, base + k * 0.5 + 0.4))
    achados = achar_duplicatas(dup_words)
    assert achados, "nao achou o recomeco de take"
    # a take ruim inteira sai (0..5) e a boa comeca em "ola" (6)
    assert achados[0]["ini"] == 0 and achados[0]["eco"] == 6, achados[0]

    # REGRESSAO: recomeco em que a PRIMEIRA palavra muda. Caso real do ACEBBOK-02
    # ("Ok, parece muita coisa mas não é" -> "Certo, parece muita coisa mas não
    # é"). Com sonda de 2 da 0.737 e passa batido; com 6 da 0.902. Este teste
    # trava a varredura multi-tamanho: voltando a sonda fixa, ele falha.
    troca = []
    for k, t in enumerate(["ok", "parece", "muita", "coisa", "mas", "nao"]):
        troca.append(w(t, k * 0.4, k * 0.4 + 0.3))
    base = 5 * 0.4 + 0.3 + 1.2                 # pausa de 1.2s antes do recomeco
    for k, t in enumerate(["certo", "parece", "muita", "coisa", "mas", "nao"]):
        troca.append(w(t, base + k * 0.4, base + k * 0.4 + 0.3))
    achados = achar_duplicatas(troca)
    assert achados and achados[0]["ini"] == 0 and achados[0]["eco"] == 6, achados

    # REGRESSAO: recomeco comecando em palavra funcional curta. Caso real do
    # ACEBBOK-02 ("O que que eu nao recomendo..." -> "O que eu nao recomendo...").
    # A sonda de 2 da "oque", 4 chars, abaixo do minimo — antes isso descartava o
    # ponto inteiro; agora so descarta aquele tamanho.
    curto = []
    for k, t in enumerate(["o", "que", "que", "eu", "nao", "recomendo"]):
        curto.append(w(t, k * 0.4, k * 0.4 + 0.3))
    base = 5 * 0.4 + 0.3 + 0.9
    for k, t in enumerate(["o", "que", "eu", "nao", "recomendo", "mas"]):
        curto.append(w(t, base + k * 0.4, base + k * 0.4 + 0.3))
    assert achar_duplicatas(curto), "recomeco em palavra funcional curta foi perdido"

    # folga no corte, com os tempos reais do "ok?" de 0.16s do ACEBBOK-02.
    # Atras ele esta colado em "ativos" (silencio zero), entao nao avanca nada.
    # Na frente ha 0.24s de silencio; metade seria 0.12, mas o teto PAD_CORTE_S
    # de 0.06 e menor e vence.
    tres = [w("ativos", 0.0, 0.64), w("ok", 0.64, 0.80), w("e", 1.04, 1.37)]
    ini, fim = faixa_palavra(tres, 1)
    assert ini == 0.64, ini
    assert abs(fim - 0.86) < 0.011, fim
    assert fim < tres[2]["start"], "a folga encostou na palavra seguinte"

    # silencio apertado: aqui metade do intervalo (0.02) e menor que o teto, e a
    # folga tem que ceder — senao ela invade a palavra seguinte
    apertado = [w("a", 0.0, 0.50), w("ok", 0.50, 0.66), w("b", 0.70, 1.00)]
    _, fim = faixa_palavra(apertado, 1)
    assert abs(fim - 0.68) < 0.011, fim
    assert fim < apertado[2]["start"]

    # encaixe no vale: curva de 1s a cada 0.01s, fala alta com um vale em 0.50s
    vale = [100.0] * 100
    vale[50] = 1.0
    assert encaixar_no_vale(vale, 0.47) == 0.50, encaixar_no_vale(vale, 0.47)
    assert encaixar_no_vale(vale, 0.55) == 0.50
    # fora do alcance de 0.15s, nao inventa: fica no minimo da janela local
    assert encaixar_no_vale(vale, 0.90) != 0.50
    # sem curva (ffmpeg falhou) devolve o tempo intacto — encaixe e melhoria
    assert encaixar_no_vale([], 1.234) == 1.234
    # tempo alem do fim da curva nao estoura indice
    assert isinstance(encaixar_no_vale(vale, 99.0), float)

    # o vale escolhido e o MENOR, nao o primeiro que aparece
    dois = [100.0] * 100
    dois[48] = 30.0
    dois[52] = 2.0
    assert encaixar_no_vale(dois, 0.50) == 0.52, encaixar_no_vale(dois, 0.50)

    # sem pausa nenhuma nao ha recomeco: fala corrida e fala corrida. Este teste
    # trava a ancora de pausa — tirando ela, a busca por texto sozinha volta a
    # inventar fronteira no meio da frase.
    plano = [w(t, k * 0.5, k * 0.5 + 0.4) for k, t in enumerate(
        ["fala", "pessoal", "hoje", "eu", "vou", "falar", "ola", "pessoal", "anderson", "aqui"])]
    assert achar_duplicatas(plano) == [], achar_duplicatas(plano)

    # texto sem repeticao nao gera candidato
    limpo = ["hoje", "vamos", "falar", "sobre", "normalizacao", "de", "audio"]
    sem = [w(t, i * 0.5, i * 0.5 + 0.4) for i, t in enumerate(limpo)]
    assert achar_duplicatas(sem) == [], achar_duplicatas(sem)

    # eco longe demais nao conta: recapitular no fim da aula nao e recomeco
    longe = [w("fala", 0, 0.4), w("pessoal", 0.5, 0.9), w("beleza", 1.0, 1.4),
             w("fala", 500, 500.4), w("pessoal", 500.5, 500.9), w("beleza", 501, 501.4)]
    assert achar_duplicatas(longe) == []

    # REGRESSAO, falso positivo real (video de 1.1 min, primeiro teste com audio
    # de verdade): "e cada" em 8.96s casou com "cada um" em 45.48s a 0.727, so
    # por compartilhar "cada", e propos cortar 36,5s de narracao boa. Tres coisas
    # matam isso — alvo curto demais, 36s nao e recomeco, e 0.727 < 0.78.
    fp = [w("e", 8.96, 9.10), w("cada", 9.15, 9.50), w("vez", 9.55, 9.90),
          w("que", 9.95, 10.20), w("voce", 10.25, 10.60),
          w("cada", 45.48, 45.85), w("um", 45.90, 46.10), w("tem", 46.15, 46.45)]
    assert achar_duplicatas(fp) == [], achar_duplicatas(fp)

    # ganho: o caso real do lote de 18 aulas. O 001 estava a -44.4 LUFS e o alvo
    # e -14, entao precisa de ~30 dB (mais a margem que o limiter come).
    assert ganho_para_alvo(-44.4) == 30.9, ganho_para_alvo(-44.4)
    assert ganho_para_alvo(-14.0) == 0.5
    assert ganho_para_alvo(-10.0) == -3.5     # fonte alta demais tambem desce

    # corte suspeito: o caso real de 163s -> 2.7s tem que disparar, e um corte
    # normal de aula (10-45% removido) nao pode disparar
    assert corte_suspeito(163.0, 2.7)
    assert corte_suspeito(307.0, 7.0)
    assert not corte_suspeito(318.0, 156.0)    # 51%, agressivo mas plausivel
    assert not corte_suspeito(69.4, 37.4)      # o teste real do usuario, 46%
    assert not corte_suspeito(100.0, 100.0)
    assert not corte_suspeito(0.0, 0.0)        # divisao por zero nao quebra

    # corte irrelevante: o caso real do "04 - COMO GERAR FOTOS", 0.7% removido
    # depois de 1h de CPU. Video ja editado nao tem tempo morto para tirar.
    assert corte_irrelevante(3600.0, 3575.0)   # 0.7%
    assert not corte_irrelevante(163.0, 142.4) # 12.6%, corte normal
    assert not corte_irrelevante(0.0, 0.0)

    # custo: tabela bate e modelo desconhecido nao quebra
    assert abs(estimar_custo(600, "deepgram/nova-3") - 0.043) < 1e-6
    assert estimar_custo(600, "modelo/inexistente") is None
    assert _fmt_custo(None) == "?"

    # .env: le a chave da skill e ignora o resto
    env = Path(tempfile.mkdtemp(prefix="remove-fillers-teste-")) / ".env"
    env.write_text("# comentario\nSENHA_DO_BANCO=nao-me-leia\n"
                   "OPENROUTER_API_KEY=sk-teste\n", encoding="utf-8")
    assert _chave_no_env(env) == "sk-teste", _chave_no_env(env)

    env.write_text('OPENROUTER_API_KEY="sk-com-aspas"\n', encoding="utf-8")
    assert _chave_no_env(env) == "sk-com-aspas"

    # chave vazia (o proprio .env.example) nao conta como achada
    env.write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
    assert _chave_no_env(env) is None

    env.write_text("SENHA_DO_BANCO=nao-me-leia\n", encoding="utf-8")
    assert _chave_no_env(env) is None

    # BOM: o que o Bloco de Notas e `Out-File -Encoding utf8` gravam no Windows.
    # Com utf-8 puro a chave viria como "﻿OPENROUTER_API_KEY" e nao casaria.
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
    gagueiras = achar_gagueiras(words)
    duplicatas = achar_duplicatas(words)

    dados = {
        "modelo_stt": modelo,
        "custo_estimado_usd": round(estimar_custo(dur, modelo) or 0, 4),
        "palavras": len(words),
        "duracao_s": round(dur, 2),
        "candidatos": {
            "gagueiras": gagueiras,
            "duplicatas": duplicatas,
        },
        "words": [{"i": i, "word": w["word"].strip(),
                   "start": round(w["start"], 2), "end": round(w["end"], 2)}
                  for i, w in enumerate(words)],
    }
    saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*72}")
    print(f"  {len(words)} palavras · {dur/60:.1f} min de fala · {modelo}")
    print(f"  custo da transcricao: {_fmt_custo(estimar_custo(dur, modelo))}")
    print(f"{'='*72}")
    print(f"  candidatos mecanicos encontrados:")
    print(f"     {len(gagueiras):3} gagueira(s)")
    print(f"     {len(duplicatas):3} duplicata(s) / recomeco(s) de take")
    print(f"{'='*72}")
    print(f"\n💾 {saida}")
    print("\nVicio de linguagem NAO foi julgado aqui: quem le este JSON, corrige a")
    print("transcricao e decide os cortes e o agente, seguindo o SKILL.md.")


if __name__ == "__main__":
    main()
