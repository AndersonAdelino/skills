#!/usr/bin/env python3
"""
remove-fillers.py — acha vicios de linguagem e gagueiras num video, com timestamp

Script da skill /cut-silence (modo --fillers).

O texto deste script fica em portugues de proposito: o modo --fillers so funciona
em PT-BR, entao quem roda ele fala portugues. O resto do repositorio e em ingles.

Transcreve com timestamp por palavra (OpenRouter /audio/transcriptions) e decide
quais palavras sao parasitas: gagueira por heuristica, filler por julgamento de LLM.
Na analise NAO corta nada: entrega as faixas para aprovacao. So o modo --aplicar
mexe em video.

Uso:
  python remove-fillers.py <video.mp4> [--json <saida.json>]     # analisa, nao corta
  python remove-fillers.py --aplicar <video.mp4> <fillers.json> <saida.mp4> [--margin 0.2s]
  python remove-fillers.py --autoteste

Saida: relatorio no terminal + JSON com {cortes: [[ini,fim], ...], cut_out: "..."}

Idioma: o julgamento de filler e calibrado para portugues brasileiro.

Requisitos:
  pip install openai auto-editor ffmpeg-normalize
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
import threading
import unicodedata
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

STT_MODEL     = "openai/whisper-large-v3-turbo"   # unico barato que devolve word timestamps
LLM_MODEL     = "meta-llama/llama-3.3-70b-instruct"
OPENROUTER    = "https://openrouter.ai/api/v1"
MAX_MB        = 15          # base64 incha ~33%, entao 15MB cru ~ 20MB no request
CHUNK_MINUTES = 18
PALAVRAS_LOTE = 300         # palavras por chamada de LLM
LLM_TIMEOUT   = 240
LLM_ATTEMPTS  = 3

# guardrails: se o LLM passar disso, ele entendeu errado a tarefa
TETO_CORTE_PCT   = 0.15     # nunca remover mais de 15% das palavras
MAX_SEQUENCIA    = 6        # nunca remover mais de 6 palavras seguidas
GAP_GAGUEIRA     = 0.6      # repeticao dentro desse intervalo = gagueira, nao enfase

# Palavras que o LLM NAO pode remover, por mais convencido que esteja.
# Vocativo: quem grava uma aula fala com a audiencia o tempo todo ("era isso, pessoal").
# Pronome: tirar o sujeito quebra a frase ("o que ele corrigiu" -> "o que corrigiu"),
# erro real observado em teste.
# Vale so para o palpite do LLM: em gagueira a palavra sobrevive numa das repeticoes.
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
    """
    for linha in env.read_text(encoding="utf-8").splitlines():
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
    """Procura a chave no ambiente; se nao achar, varre .env subindo as pastas.

    Assim funciona tanto com um .env na raiz de um projeto quanto na maquina de
    alguem que so largou um .env do lado do script.
    """
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


def _llm_once(client, prompt: str):
    """Timeout de leitura nao dispara se o provider goteja bytes sem terminar;
    thread daemon + join(timeout) abandona a chamada e nao trava a saida."""
    resultado = {}

    def chamar():
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=8192,
            )
            resultado["texto"] = resp.choices[0].message.content.strip()
        except Exception as e:                      # noqa: BLE001
            resultado["erro"] = e

    t = threading.Thread(target=chamar, daemon=True)
    t.start()
    t.join(timeout=LLM_TIMEOUT)

    if t.is_alive():
        return None, f"timeout ({LLM_TIMEOUT}s)"
    if "erro" in resultado:
        return None, str(resultado["erro"])
    return resultado.get("texto"), None


# ── deteccao de gagueira (heuristica pura, sem LLM) ───────────────────────────

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


def validar(words: list, indices: list, gagueiras: set = frozenset()) -> tuple:
    """Devolve (indices_limpos, avisos). Descarta o que viola guardrail.

    `gagueiras` sao indices vindos da heuristica, isentos da lista PROTEGIDO:
    numa repeticao a palavra sobrevive numa das ocorrencias, entao remover as
    outras nao apaga sentido nenhum.
    """
    avisos = []
    n = len(words)
    limpos = sorted({i for i in indices if isinstance(i, int) and 0 <= i < n})

    descartados = len(set(indices)) - len(limpos)
    if descartados > 0:
        avisos.append(f"{descartados} indice(s) fora da faixa 0..{n-1}, descartados")

    # nunca remover sequencia longa demais
    fora = []
    seq, ini = [], None
    for i in limpos + [None]:
        if seq and (i is None or i != seq[-1] + 1):
            if len(seq) > MAX_SEQUENCIA:
                fora.extend(seq)
            seq = []
        if i is not None:
            seq.append(i)
    if fora:
        avisos.append(f"{len(fora)} palavra(s) em bloco maior que {MAX_SEQUENCIA} seguidas, descartadas")
        limpos = [i for i in limpos if i not in set(fora)]

    # nunca deixar o LLM cortar vocativo nem pronome (gagueira e isenta)
    prot = [i for i in limpos
            if i not in gagueiras and _norm(words[i]["word"]) in PROTEGIDO]
    if prot:
        amostra = ", ".join(sorted({words[i]["word"].strip() for i in prot})[:5])
        avisos.append(f"{len(prot)} palavra(s) protegida(s) recusada(s) ao LLM ({amostra})")
        limpos = [i for i in limpos if i not in set(prot)]

    return limpos, avisos


# ── transcricao via OpenRouter ────────────────────────────────────────────────

def transcrever(video: Path) -> list:
    import base64
    import urllib.request
    import urllib.error

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
    audio = tmp / f"{slugify(video.stem)}_vicios.mp3"
    print(f"🎵 extraindo audio...", flush=True)
    extract_audio(video, audio)

    def _post(b64: str) -> dict:
        payload = {
            "model": STT_MODEL,
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
        print(f"🎧 transcrevendo ({mb:.1f} MB, {STT_MODEL})...", flush=True)
        words = _post(base64.b64encode(audio.read_bytes()).decode()).get("words") or []
    else:
        total = get_duration(audio)
        passo = CHUNK_MINUTES * 60
        n = -(-int(total) // int(passo))
        print(f"🎧 transcrevendo em {n} partes ({mb:.1f} MB)...", flush=True)
        for i in range(n):
            parte = tmp / f"vicios_chunk_{i}.mp3"
            ini = i * passo
            extract_chunk(audio, parte, ini, min(passo, total - ini))
            print(f"   parte {i+1}/{n}...", flush=True)
            for w in (_post(base64.b64encode(parte.read_bytes()).decode()).get("words") or []):
                words.append({"word": w["word"], "start": w["start"] + ini, "end": w["end"] + ini})
            parte.unlink(missing_ok=True)

    audio.unlink(missing_ok=True)
    return words


# ── julgamento do LLM ─────────────────────────────────────────────────────────

PROMPT = """\
Voce recebe a transcricao de uma AULA GRAVADA em portugues brasileiro, com cada \
palavra numerada. Sua tarefa e apontar SOMENTE as palavras que sao vicio de \
linguagem puro: som parasita que pode sair sem mudar nada do sentido.

REMOVA:
- Bordao vazio: "né", "hum", "ahn", "é é é" hesitante
- "tipo" quando significa "assim/mais ou menos" (nao quando significa categoria)
- "tá" de confirmacao no fim de frase ("beleza, tá?")
- Comeco de frase abandonado: a pessoa comeca, se corrige e recomeca
- Palavra gaguejada repetida

NUNCA REMOVA:
- Vocativo: "pessoal", "galera", "gente", "cara" quando ele fala COM a audiencia
- "então", "aí", "olha", "bom", "agora" quando ligam raciocinio (quase sempre ligam)
- Qualquer palavra que carregue sentido: verbo, substantivo, nome de ferramenta
- Palavra que, tirada, deixa a frase quebrada ou ambigua

Na duvida, NAO remova. Errar deixando um "né" e barato; errar cortando uma \
palavra de conteudo estraga a aula.

Devolva SOMENTE um JSON, sem comentario, no formato:
{{"cortar": [12, 45, 46]}}

PALAVRAS:
{trecho}"""


def julgar(words: list) -> list:
    from openai import OpenAI

    carregar_env()
    client = OpenAI(base_url=OPENROUTER, api_key=os.environ["OPENROUTER_API_KEY"],
                    timeout=LLM_TIMEOUT, max_retries=0)

    achados = []
    for ini in range(0, len(words), PALAVRAS_LOTE):
        fim = min(ini + PALAVRAS_LOTE, len(words))
        trecho = " ".join(f"[{i}]{words[i]['word'].strip()}" for i in range(ini, fim))
        print(f"   🤔 julgando palavras {ini}-{fim}...", flush=True)

        for tentativa in range(LLM_ATTEMPTS):
            texto, err = _llm_once(client, PROMPT.format(trecho=trecho))
            if texto:
                m = re.search(r"\{.*\}", texto, re.S)
                if m:
                    try:
                        lista = json.loads(m.group(0)).get("cortar", [])
                        achados.extend(int(x) for x in lista if isinstance(x, (int, float)))
                        break
                    except (json.JSONDecodeError, ValueError, TypeError):
                        err = "JSON invalido"
                else:
                    err = "sem JSON na resposta"
            resto = "" if tentativa == LLM_ATTEMPTS - 1 else " — tentando de novo"
            print(f"   ⚠️  {err}{resto}", flush=True)
    return achados


# ── relatorio ─────────────────────────────────────────────────────────────────

def contexto(words: list, i: int, janela: int = 4) -> str:
    ini, fim = max(0, i - janela), min(len(words), i + janela + 1)
    return " ".join(
        (f"[{w['word'].strip()}]" if k == i else w["word"].strip())
        for k, w in enumerate(words[ini:fim], start=ini)
    )


def relatorio(words: list, indices: list, gagueiras: set, avisos: list) -> dict:
    faixas = indices_para_faixas(words, indices)
    total_s = sum(f - i for i, f in faixas)
    dur = words[-1]["end"] if words else 0

    print(f"\n{'='*70}")
    print(f"palavras transcritas: {len(words)}   duracao falada: {dur/60:.1f} min")
    print(f"cortes propostos: {len(faixas)}   tempo removido: {total_s:.1f}s "
          f"({total_s/dur*100:.1f}% da fala)" if dur else "")
    for a in avisos:
        print(f"⚠️  {a}")
    print(f"{'='*70}\n")

    for i in sorted(indices):
        tag = "gagueira" if i in gagueiras else "filler"
        print(f"  {words[i]['start']:7.2f}s  {tag:9} → {contexto(words, i)}")

    return {
        "modelo_stt": STT_MODEL,
        "palavras": len(words),
        "duracao_s": round(dur, 2),
        "removido_s": round(total_s, 2),
        "cortes": [[round(a, 2), round(b, 2)] for a, b in faixas],
        "cut_out": " ".join(f"{a:.2f}sec,{b:.2f}sec" for a, b in faixas),
    }


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

    # guardrail: vocativo protegido mesmo se o LLM pedir
    voc = [w("obrigado", 0, 1), w("pessoal", 1, 2)]
    limpos, avisos = validar(voc, [1])
    assert limpos == [] and any("protegida" in a for a in avisos), (limpos, avisos)

    # guardrail: pronome protegido — o erro real observado ("o que [ele] corrigiu")
    pron = [w("que", 0, 1), w("ele", 1, 2), w("corrigiu", 2, 3)]
    assert validar(pron, [1])[0] == []

    # ...mas gagueira e isenta: 'eu eu eu acho' precisa perder as repeticoes,
    # senao a protecao de pronome mataria o recurso de gagueira
    gag = [w("eu", 0.0, 0.2), w("eu", 0.25, 0.45), w("eu", 0.5, 0.7), w("acho", 0.75, 1.1)]
    idx = achar_gagueiras(gag)
    assert validar(gag, idx, gagueiras=set(idx))[0] == [0, 1], validar(gag, idx, set(idx))

    # .env: le a chave da skill e ignora o resto. A skill roda dentro do projeto
    # dos outros, entao credencial alheia nao pode entrar junto.
    env = Path(tempfile.mkdtemp(prefix="remove-fillers-teste-")) / ".env"
    env.write_text("# comentario\nSENHA_DO_BANCO=nao-me-leia\n"
                   "OPENROUTER_API_KEY=sk-teste\n", encoding="utf-8")
    assert _chave_no_env(env) == "sk-teste", _chave_no_env(env)

    env.write_text('OPENROUTER_API_KEY="sk-com-aspas"\n', encoding="utf-8")
    assert _chave_no_env(env) == "sk-com-aspas"

    # chave vazia (o proprio .env.example) nao conta como achada, senao a busca
    # para num arquivo de exemplo e nunca chega no .env de verdade
    env.write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
    assert _chave_no_env(env) is None

    env.write_text("SENHA_DO_BANCO=nao-me-leia\n", encoding="utf-8")
    assert _chave_no_env(env) is None
    shutil.rmtree(env.parent, ignore_errors=True)

    print("✅ autoteste passou")


# ── main ──────────────────────────────────────────────────────────────────────

def aplicar(video: Path, dados: Path, saida: Path, margin: str = "0.2s"):
    """Corta silencio + vicios num passe so e normaliza o audio.

    O --cut-out do auto-editor 29.x aceita UMA faixa por ocorrencia, apesar do
    help anunciar `[START,STOP ...]`. Passar varias de uma vez faz ele tratar a
    ultima como arquivo de entrada ("Could not open input file: 432.42sec,...").
    Por isso a flag e repetida uma vez por faixa.

    `margin` segue a mesma regra do SKILL.md: 0.2s para aula/tutorial, 0.0s para
    anuncio e corte curto, onde cada respiro preservado derruba o ritmo.
    """
    info = json.loads(dados.read_text(encoding="utf-8"))
    faixas = []
    for a, b in info["cortes"]:
        faixas += ["--cut-out", f"{a:.2f}sec,{b:.2f}sec"]
    if not faixas:
        print("Nada a cortar: o JSON nao tem faixas.")
        sys.exit(1)

    tmp_dir = saida.parent / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cache = tmp_dir / f"cache_{slugify(video.stem)}"
    corte = tmp_dir / f"{slugify(video.stem)}_corte.mp4"

    print(f"✂️  cortando silencio + {len(faixas)//2} vicio(s) (margin {margin})...", flush=True)
    r = subprocess.run(
        ["auto-editor", str(video), "--edit", "audio:threshold=4%", "--margin", margin,
         *faixas, "--temp-dir", str(cache), "-o", str(corte), "--no-open"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    shutil.rmtree(cache, ignore_errors=True)
    if r.returncode != 0 or not corte.exists():
        print(f"ERRO no auto-editor:\n{(r.stderr or r.stdout)[-800:]}")
        sys.exit(1)

    print("🔊 normalizando audio (-16 LUFS)...", flush=True)
    r = subprocess.run(
        ["ffmpeg-normalize", str(corte), "-o", str(saida), "-c:a", "aac", "-b:a", "192k",
         "-t", "-16", "-tp", "-1.5", "--auto-lower-loudness-target", "-f"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 or not saida.exists():
        print(f"ERRO na normalizacao:\n{(r.stderr or r.stdout)[-800:]}")
        sys.exit(1)
    corte.unlink(missing_ok=True)
    # nao deixar um _tmp vazio na pasta de saida do usuario; se sobrou coisa
    # de outra execucao rodando junto, o rmdir falha e a pasta fica, que e o certo
    try:
        tmp_dir.rmdir()
    except OSError:
        pass

    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(saida)],
                         capture_output=True, text=True).stdout.strip()
    print(f"\n✅ {saida}\n   duracao final: {float(dur)/60:.1f} min")


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

    if "--aplicar" in args:
        resto = [a for a in args if a != "--aplicar"]
        if len(resto) != 3:
            print("Uso: --aplicar <video.mp4> <fillers.json> <saida.mp4> [--margin 0.2s]")
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
        words = transcrever(video)
    except RuntimeError as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    if not words:
        print("Erro: transcricao voltou sem timestamps por palavra.")
        sys.exit(1)

    gagueiras = set(achar_gagueiras(words))
    print(f"🔁 gagueiras (heuristica): {len(gagueiras)}")

    print(f"🧠 julgando fillers com {LLM_MODEL}...")
    do_llm = julgar(words)

    limpos, avisos = validar(words, list(gagueiras) + do_llm, gagueiras=gagueiras)

    pct = len(limpos) / len(words) if words else 0
    if pct > TETO_CORTE_PCT:
        print(f"\n❌ ABORTADO: o julgamento marcou {pct*100:.0f}% das palavras "
              f"(teto e {TETO_CORTE_PCT*100:.0f}%). Isso nao e vicio de linguagem, "
              f"e erro de interpretacao. Nada foi cortado.")
        sys.exit(1)

    dados = relatorio(words, limpos, gagueiras, avisos)
    saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 {saida}")
    print(f"\nPara aplicar, o /cut-silence passa ao auto-editor:\n  --cut-out {dados['cut_out'][:120]}...")


if __name__ == "__main__":
    main()
