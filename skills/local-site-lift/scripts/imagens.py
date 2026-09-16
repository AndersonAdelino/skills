#!/usr/bin/env python3
"""
imagens.py - resolve as imagens de um site: busca, gera, baixa e otimiza.

  buscar "<termo>" [--n 5] [--previa <pasta>]   ve o que existe no Pexels
  pegar <id> --out img/hero                     baixa a foto escolhida
  gerar "<prompt>" --out img/x [--aspect 16:9]  kie.ai (CUSTA CREDITO)
  baixar <url> --out img/y                      qualquer URL de imagem
  otimizar <arquivo> --out img/z                so redimensiona e converte
  --autoteste                                   asserts, sem rede e sem chave

Todo comando termina igual: confere os BYTES, redimensiona, converte para webp
e informa o peso final. Imagem pesada e o que mais atrasa site de comercio
local no 4G.

Chaves no .env, so as que precisa: PEXELS_API_KEY, KIE_API_KEY.

`buscar` e `pegar` sao separados de proposito. O primeiro resultado do Pexels
costuma estar errado: numa busca por "familia feliz" para uma clinica no Seridao
veio uma marina com bandeira dos EUA. Olhe as previas antes de escolher.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# O Pexels fica atras do Cloudflare, que recusa requisicao sem User-Agent com
# 403 e "error code: 1010". Sem este header a busca nunca funciona.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

PEXELS = "https://api.pexels.com/v1/search"
KIE_CRIAR = "https://api.kie.ai/api/v1/jobs/createTask"
KIE_STATUS = "https://api.kie.ai/api/v1/jobs/recordInfo"   # nao getTaskDetail
KIE_MODELO = "nano-banana-2"
KIE_TIMEOUT = 600

LARGURA_PADRAO = 1280
QUALIDADE = 78
ALVO_KB = 150          # acima disso o script reclama


class Erro(RuntimeError):
    """Problema previsto, vira mensagem em vez de traceback."""


# ── chaves ────────────────────────────────────────────────────────────────────

def _chave_no_env(env: Path, nome: str):
    """Le SOMENTE a chave pedida, como utf-8-sig.

    utf-8-sig porque Bloco de Notas e `Out-File -Encoding utf8` gravam BOM no
    Windows, e com utf-8 puro a primeira chave do arquivo nunca casa com o nome.
    So a chave pedida porque o .env do projeto de um cliente costuma ter
    credencial que nao tem nada a ver com imagem.
    """
    for linha in env.read_text(encoding="utf-8-sig").splitlines():
        if linha.lstrip().startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        if k.strip() == nome:
            v = v.strip().strip('"').strip("'")
            if v:
                return v
    return None


def carregar_chave(nome: str, onde: str) -> str:
    if os.environ.get(nome):
        return os.environ[nome]
    vistos = set()
    for partida in (Path.cwd(), Path(__file__).resolve().parent):
        for pasta in [partida, *partida.parents][:6]:
            env = pasta / ".env"
            if env in vistos or not env.exists():
                continue
            vistos.add(env)
            achou = _chave_no_env(env, nome)
            if achou:
                return achou
    cmd = (f'  $env:{nome} = "sua-chave"' if sys.platform == "win32"
           else f'  export {nome}="sua-chave"')
    raise Erro(f"falta a chave {nome}. Pegue em {onde} e defina:\n\n{cmd}\n\n"
               f"Ou grave num .env como  {nome}=sua-chave")


# ── http ──────────────────────────────────────────────────────────────────────

def _http(url, dados=None, headers=None, timeout=90) -> bytes:
    h = dict(headers or {})
    h.setdefault("User-Agent", UA)
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, data=dados, headers=h),
                timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        corpo = e.read()[:200].decode("utf-8", "replace").strip()
        if "1010" in corpo:
            raise Erro("o Cloudflare recusou a requisicao (403, error code "
                       "1010). Falta User-Agent, que este script envia: se "
                       "apareceu, o servico esta bloqueando seu IP.") from None
        raise Erro(f"HTTP {e.code} em {url.split('?')[0]}: {corpo}") from None
    except urllib.error.URLError as e:
        raise Erro(f"nao consegui falar com {url.split('?')[0]}: "
                   f"{getattr(e, 'reason', e)}") from None


def _json(url, dados=None, headers=None, timeout=90):
    h = dict(headers or {})
    if dados is not None:
        h["Content-Type"] = "application/json"
        dados = json.dumps(dados).encode()
    return json.loads(_http(url, dados, h, timeout))


def headers_pexels(chave: str) -> dict:
    """Os DOIS headers sao obrigatorios: sem User-Agent, 403 em tudo."""
    return {"Authorization": chave, "User-Agent": UA}


# ── bytes ─────────────────────────────────────────────────────────────────────

def tipo_imagem(b: bytes):
    """Identifica pelo conteudo. None = nao e imagem."""
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:2] == b"\xff\xd8":
        return "jpg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def gravar(dados: bytes, destino: Path) -> Path:
    """Grava conferindo os bytes. Pagina de erro salva com extensao de imagem e
    o jeito classico de "o arquivo existe" mentir."""
    tipo = tipo_imagem(dados)
    if not tipo:
        raise Erro(f"o que veio nao e imagem ({len(dados)} bytes). "
                   "A URL pode ser de uma pagina, nao do arquivo.")
    destino = destino.with_suffix("." + tipo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)
    return destino


# ── otimizacao ────────────────────────────────────────────────────────────────

def comando_ffmpeg(entrada: Path, saida: Path, largura: int) -> list:
    """`-2` mantem a proporcao e forca altura par, que o encoder exige."""
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(entrada),
            "-vf", f"scale={largura}:-2", "-c:v", "libwebp",
            "-quality", str(QUALIDADE), "-compression_level", "6", str(saida)]


def otimizar(arquivo: Path, largura=LARGURA_PADRAO):
    """Redimensiona e converte para webp. Sem ffmpeg, mantem o original.

    Nao e obrigatorio de proposito: a skill promete rodar so com Python. Mas
    sem esta etapa uma imagem gerada chega com 1,7 MB, e o site perde o unico
    argumento que ele tem, que e abrir rapido.
    """
    if not shutil.which("ffmpeg"):
        kb = arquivo.stat().st_size // 1024
        print(f"  aviso: sem ffmpeg, mantive {arquivo.name} como veio "
              f"({kb} KB). Instale ffmpeg para reduzir, ou comprima a mao.")
        return arquivo
    saida = arquivo.with_suffix(".webp")
    if saida == arquivo:
        saida = arquivo.with_name(arquivo.stem + "-otim.webp")
    r = subprocess.run(comando_ffmpeg(arquivo, saida, largura),
                       capture_output=True, timeout=180)
    if r.returncode != 0 or not saida.exists():
        print(f"  aviso: ffmpeg falhou, mantive o original. "
              f"{r.stderr[:160].decode('utf-8', 'replace')}")
        return arquivo
    if saida != arquivo:
        arquivo.unlink(missing_ok=True)
    return saida


def relatar(caminho: Path) -> Path:
    kb = caminho.stat().st_size // 1024
    aviso = f"   <- acima de {ALVO_KB} KB, considere reduzir" if kb > ALVO_KB else ""
    print(f"{caminho}  ({kb} KB){aviso}")
    return caminho


# ── Pexels ────────────────────────────────────────────────────────────────────

def buscar(termo: str, n=5, previa: Path = None):
    """Lista candidatos. Baixa previas pequenas se `previa` for dado, para o
    agente OLHAR antes de escolher."""
    chave = carregar_chave("PEXELS_API_KEY", "https://www.pexels.com/api/")
    url = PEXELS + "?" + urllib.parse.urlencode(
        {"query": termo, "per_page": max(1, min(n, 15)),
         "orientation": "landscape"})
    r = _json(url, None, headers_pexels(chave))
    fotos = r.get("photos") or []
    if not fotos:
        raise Erro(f"o Pexels nao achou nada para '{termo}'. Tente em ingles, "
                   "ou com termos mais comuns.")
    print(f"{r.get('total_results')} resultados para '{termo}':\n")
    for f in fotos:
        print(f"  id={f['id']:<10} {f.get('photographer','?')[:24]:<26} "
              f"{f['width']}x{f['height']}")
        print(f"      {f.get('alt') or '(sem descricao)'}"[:96])
    if previa:
        previa.mkdir(parents=True, exist_ok=True)
        print("\nprevias para olhar:")
        for f in fotos:
            b = _http(f["src"]["medium"])
            p = gravar(b, previa / f"previa-{f['id']}")
            print(f"  {p}")
    print("\nEscolha e rode:  imagens.py pegar <id> --out img/<nome>")
    return fotos


def pegar(foto_id: str, destino: Path, largura=LARGURA_PADRAO):
    chave = carregar_chave("PEXELS_API_KEY", "https://www.pexels.com/api/")
    r = _json(f"https://api.pexels.com/v1/photos/{foto_id}", None,
              headers_pexels(chave))
    autor = r.get("photographer", "?")
    b = _http(r["src"]["large2x"])
    arq = otimizar(gravar(b, destino), largura)
    print(f"credito: {autor}, via Pexels ({r.get('url','')})")
    return relatar(arq)


# ── kie.ai ────────────────────────────────────────────────────────────────────

def url_do_resultado(data: dict) -> str:
    """A URL vem em data.resultJson, que e uma STRING json aninhada."""
    out = data.get("resultJson")
    if isinstance(out, str):
        out = json.loads(out)
    urls = (out or {}).get("resultUrls") or (out or {}).get("result_urls") or []
    if not urls:
        raise Erro(f"a kie.ai terminou sem URL de resultado: {data}")
    return urls[0]


def gerar(prompt: str, destino: Path, aspect="16:9", largura=LARGURA_PADRAO,
          modelo=KIE_MODELO):
    chave = carregar_chave("KIE_API_KEY", "https://kie.ai")
    h = {"Authorization": f"Bearer {chave}"}
    r = _json(KIE_CRIAR, {"model": modelo,
                          "input": {"prompt": prompt, "aspect_ratio": aspect}}, h)
    if r.get("code") != 200 or not (r.get("data") or {}).get("taskId"):
        raise Erro(f"a kie.ai recusou a task: {r}")
    task = r["data"]["taskId"]
    print(f"kie.ai task {task} ...", flush=True)
    inicio, espera = time.time(), 4.0
    while True:
        passou = time.time() - inicio
        if passou > KIE_TIMEOUT:
            raise Erro(f"a kie.ai passou de {KIE_TIMEOUT // 60} min na task "
                       f"{task}. Confira os creditos em https://kie.ai")
        d = (_json(f"{KIE_STATUS}?taskId={urllib.parse.quote(task)}", None, h)
             .get("data") or {})
        estado = d.get("state") or d.get("status")
        if estado == "success":
            b = _http(url_do_resultado(d))
            return relatar(otimizar(gravar(b, destino), largura))
        if estado in ("fail", "failed", "error"):
            raise Erro(f"a kie.ai falhou: {d.get('failMsg') or d}")
        print(f"  {estado or 'na fila'} ({int(passou)}s)", flush=True)
        time.sleep(espera)
        espera = min(espera * 1.25, 15.0)


# ── autoteste ─────────────────────────────────────────────────────────────────

def autoteste():
    import tempfile

    # ── o bug que custou tempo: sem User-Agent o Pexels devolve 403/1010 ────
    h = headers_pexels("chave-de-teste")
    assert h["Authorization"] == "chave-de-teste"
    assert h["User-Agent"].startswith("Mozilla/"), \
        "sem User-Agent o Pexels devolve 403 para todo mundo"

    # ── a kie.ai devolve resultJson como STRING json aninhada ───────────────
    assert url_do_resultado(
        {"resultJson": '{"resultUrls":["https://cdn.kie.ai/a.png"]}'}
    ) == "https://cdn.kie.ai/a.png"
    assert url_do_resultado(
        {"resultJson": {"resultUrls": ["https://cdn.kie.ai/b.png"]}}
    ) == "https://cdn.kie.ai/b.png"
    for ruim in ({"resultJson": '{"resultUrls":[]}'}, {}, {"resultJson": "{}"}):
        try:
            url_do_resultado(ruim)
            raise AssertionError("sem URL tinha que estourar")
        except Erro:
            pass
    assert KIE_STATUS.endswith("recordInfo"), "getTaskDetail devolve 404"

    # ── bytes, nao extensao: e o que separa imagem de pagina de erro ────────
    assert tipo_imagem(b"\x89PNG\r\n\x1a\n" + b"\0" * 8) == "png"
    assert tipo_imagem(b"\xff\xd8\xff\xe0") == "jpg"
    assert tipo_imagem(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert tipo_imagem(b"<!doctype html><title>404") is None

    tmp = Path(tempfile.mkdtemp(prefix="img-teste-"))
    try:
        # extensao vem do conteudo, nao do nome que pediram
        p = gravar(b"\xff\xd8\xff\xe0dados", tmp / "hero")
        assert p.name == "hero.jpg", p
        p2 = gravar(b"RIFF\x00\x00\x00\x00WEBPVP8 x", tmp / "hero.png")
        assert p2.name == "hero.webp", p2
        try:
            gravar(b"<html>erro 404</html>", tmp / "x")
            raise AssertionError("pagina de erro tinha que estourar")
        except Erro:
            pass

        # ── ffmpeg: proporcao mantida e altura par ──────────────────────────
        cmd = comando_ffmpeg(tmp / "a.jpg", tmp / "a.webp", 1280)
        assert "scale=1280:-2" in cmd, cmd
        assert "libwebp" in cmd and "-y" in cmd
        i = cmd.index("-quality")
        assert 1 <= int(cmd[i + 1]) <= 100

        # sem ffmpeg o arquivo sobrevive, so avisa: a skill promete rodar so
        # com Python, e imagem grande e melhor que imagem nenhuma
        orig, which = tmp / "b.jpg", shutil.which
        orig.write_bytes(b"\xff\xd8" + b"x" * 5000)
        shutil.which = lambda _: None
        try:
            assert otimizar(orig) == orig and orig.exists()
        finally:
            shutil.which = which

        # ── .env: BOM, e a chave vizinha nao vaza ───────────────────────────
        env = tmp / ".env"
        env.write_text("PEXELS_API_KEY=pex123\nCPANEL_TOKEN=nao-e-da-minha-conta\n",
                       encoding="utf-8-sig")
        assert env.read_bytes().startswith(b"\xef\xbb\xbf"), "o teste precisa do BOM"
        assert _chave_no_env(env, "PEXELS_API_KEY") == "pex123"
        assert _chave_no_env(env, "KIE_API_KEY") is None
        vazia = tmp / "v.env"
        vazia.write_text("PEXELS_API_KEY=\n# KIE_API_KEY=comentada\n", encoding="utf-8")
        assert _chave_no_env(vazia, "PEXELS_API_KEY") is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("✅ autoteste passou")


# ── cli ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Resolve as imagens de um site.")
    p.add_argument("comando", nargs="?",
                   choices=["buscar", "pegar", "gerar", "baixar", "otimizar"])
    p.add_argument("alvo", nargs="?", help="termo, id, prompt, url ou arquivo")
    p.add_argument("--out", help="caminho de saida, sem extensao")
    p.add_argument("--largura", type=int, default=LARGURA_PADRAO)
    p.add_argument("--aspect", default="16:9", help="so no gerar")
    p.add_argument("--modelo", default=KIE_MODELO, help="so no gerar")
    p.add_argument("--n", type=int, default=5, help="so no buscar")
    p.add_argument("--previa", help="pasta para baixar previas pequenas")
    p.add_argument("--autoteste", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()

    if a.autoteste:
        autoteste()
        return 0
    if not a.comando or not a.alvo:
        p.print_help()
        return 1
    if a.comando == "buscar":
        buscar(a.alvo, a.n, Path(a.previa) if a.previa else None)
        return 0

    if not a.out:
        raise Erro(f"{a.comando} precisa de --out")
    out = Path(a.out)
    if a.comando == "pegar":
        pegar(a.alvo, out, a.largura)
    elif a.comando == "gerar":
        gerar(a.alvo, out, a.aspect, a.largura, a.modelo)
    elif a.comando == "baixar":
        relatar(otimizar(gravar(_http(a.alvo), out), a.largura))
    elif a.comando == "otimizar":
        origem = Path(a.alvo)
        if not origem.exists():
            raise Erro(f"nao achei {origem}")
        relatar(otimizar(gravar(origem.read_bytes(), out), a.largura))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Erro as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
