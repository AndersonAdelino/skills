#!/usr/bin/env python3
"""
build-carousel.py - monta carrossel estilo thread do Twitter para o Instagram.

O texto deste script fica em portugues de proposito: quem le e depura ele e o
mesmo publico da skill. O resto do repositorio e em ingles.

Autocontido de proposito: so stdlib. A skill precisa funcionar copiada sozinha
para outra maquina, sem pip install. Render e screenshot do Chrome ou do Edge,
que ja existem em qualquer maquina que use essas skills.

  montar <spec.json> --out <pasta>     spec -> HTML -> PNG 1080x1350 + preview
  imagem "<prompt>" --out <png>        gera no kie.ai e BAIXA (custa credito)
  stock "<busca>" --out <png>          busca no Pexels e baixa
  baixar <url> --out <png>             baixa uma URL que o agente achou na web
  --autoteste                          roda os asserts, sem rede e sem chave

Formato do spec:

  {
    "perfil": {"nome": "...", "arroba": "@...", "avatar": "perfil.jpg"},
    "slides": [
      {"texto": "...", "imagens": ["a.jpg", "b.jpg"]},
      {"texto": "...", "card": {"fonte": "g1", "cor": "#c4170c",
                                "chapeu": "TECNOLOGIA", "titulo": "...",
                                "texto": "..."}},
      {"texto": "...", "citacao": {"texto": "...", "destaque": "..."}}
    ]
  }

Caminhos de imagem no spec sao relativos a pasta do proprio spec.
"""

import base64
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── medidas do slide ──────────────────────────────────────────────────────────
#
# 1080x1350 e o 4:5, o formato mais alto que o Instagram aceita no feed. Todo
# numero daqui pra baixo foi medido no carrossel de referencia, nao chutado.

LARGURA, ALTURA = 1080, 1350
PADDING = 64
FONTE_BASE, FONTE_PISO = 46, 36  # a faixa em que o JS procura o corpo do texto
ENTRELINHA = 1.38
GAP_PARAGRAFO = 30

KIE_MODELO = "nano-banana-2"
KIE_TIMEOUT = 600                # 10 min. sem isso, task travada trava a sessao

ASSETS = Path(__file__).resolve().parent.parent / "assets"


# ── fonte e emoji: a diferenca entre "parecido" e "igual" ─────────────────────
#
# Fonte de sistema renderizava Segoe UI no Windows, San Francisco no Mac e
# sabe-se la o que no Linux - o mesmo spec saia com cara diferente em cada
# maquina. A Inter vai embutida em base64: uma fonte so, offline, identica em
# todo lugar, e a mais proxima da Chirp que o Twitter usa.
#
# Emoji, idem: o Windows desenha a sirene do Segoe UI Emoji, que nao e a que
# aparece no print do Twitter. O Twemoji e justamente o conjunto do Twitter,
# entao ele e a escolha certa aqui, nao um remendo.

def _fonte_embutida() -> str:
    faces = []
    for peso in (400, 700):
        arq = ASSETS / "fonts" / f"inter-{peso}.woff2"
        if not arq.exists():
            return ""              # sem a fonte, cai no stack do sistema
        b64 = base64.b64encode(arq.read_bytes()).decode()
        faces.append(
            "@font-face{font-family:'Inter';font-style:normal;"
            f"font-weight:{peso};font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return "".join(faces)


# Faixas de emoji de verdade. As setas simples (U+2190-U+21FF) ficam de FORA de
# proposito: a "→" das listas e caractere de texto, nao emoji, e o Twemoji nao
# tem arquivo para ela.
EMOJI = re.compile(
    "(?:[\U0001F000-\U0001FAFF☀-➿⬀-⯿]"
    "[\U0001F3FB-\U0001F3FF️]*"
    "(?:‍[\U0001F000-\U0001FAFF☀-➿][\U0001F3FB-\U0001F3FF️]*)*)")

TWEMOJI_CDN = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72/"


def codigo_twemoji(seq: str) -> str:
    """Nome do arquivo no Twemoji. Tira o seletor de variacao (FE0F), a nao ser
    que a sequencia use ZWJ - e a mesma regra do proprio Twemoji."""
    if "‍" not in seq:
        seq = seq.replace("️", "")
    return "-".join(f"{ord(c):x}" for c in seq)


def _png_do_emoji(seq: str, cache: Path):
    """Arquivo local do emoji: primeiro o que veio junto com a skill, depois o
    cache do carrossel, e so entao a rede. None = deixa como texto."""
    code = codigo_twemoji(seq)
    if not code:
        return None
    embarcado = ASSETS / "emoji" / f"{code}.png"
    if embarcado.exists():
        return embarcado
    baixado = cache / f"{code}.png"
    if baixado.exists():
        return baixado
    try:
        dados = _http(TWEMOJI_CDN + code + ".png", timeout=20)
    except RuntimeError:
        return None                # sem rede ou emoji fora do Twemoji
    if not tipo_imagem(dados):
        return None
    cache.mkdir(parents=True, exist_ok=True)
    baixado.write_bytes(dados)
    return baixado


def trocar_emoji(marcado: str, cache: Path) -> str:
    """Troca emoji por <img> do Twemoji. Recebe HTML ja escapado."""
    def troca(m):
        arq = _png_do_emoji(m.group(0), cache)
        if not arq:
            return m.group(0)
        return f'<img class="emo" src="{_uri(arq)}" alt="">'
    return EMOJI.sub(troca, marcado)


# ── quem decide se o texto cabe ───────────────────────────────────────────────
#
# Ninguem aqui. Quem decide e o layout do browser, dentro da propria pagina.
#
# A primeira versao estimava as linhas em Python por largura media de
# caractere. Medindo o Chrome com o texto real do carrossel de referencia, nao
# existe UM valor de caracteres-por-linha que reproduza o browser: a 40px uma
# frase precisa de mais de 52 ch/linha e outra de no maximo 43, na mesma caixa.
# Estimativa de fonte fixa contra texto variavel e exatamente o padrao de bug
# do MISTAKES.md, e essa ja tinha dado falso positivo no primeiro render real.
# Entao a estimativa morreu: o JS mede as caixas de verdade.
#
# O tamanho e UM SO para o carrossel inteiro, o maior em que TODOS os slides
# cabem. Por isso toda pagina carrega todos os slides (os invisiveis so para
# medir) e chega sozinha na mesma resposta, sem processo nenhum conversando com
# outro. Fonte diferente por slide renderiza sem erro e entrega um carrossel
# com cara de amador.
#
# O piso e 36px, nao 30. Com piso baixo demais UM slide gigante derruba o
# carrossel INTEIRO para a fonte minima, sem erro nenhum: aconteceu no primeiro
# teste, o slide de gancho caiu de 46px para 30px porque outro slide tinha 1739
# caracteres. Um slide que nao cabe a 36px nao encolhe os outros, ele leva a
# barra vermelha e tem que ser reescrito. Este formato nao e para paredao de
# texto.

# Maior texto que cabe a 46px, por tipo de bloco. Medido no Chrome com busca
# binaria sobre prosa PT-BR real, nao estimado.
#
#   fonte   so texto   com foto   com card
#    46px        619        336        422
#    36px        955        610        682
#
# Isto NAO preve o render (quem decide e o browser). Serve para uma coisa so:
# apontar QUAL slide esta puxando o carrossel para baixo, que e justamente o
# que o browser nao conta, porque ele so aplica o resultado em silencio.
ORCAMENTO_46 = {None: 619, "imagens": 336, "card": 422, "citacao": 422}


def tipo_do_bloco(slide: dict):
    presentes = [k for k in ("imagens", "card", "citacao") if slide.get(k)]
    if len(presentes) > 1:
        raise RuntimeError(
            f"slide com mais de um bloco visual ({', '.join(presentes)}). "
            "Cada slide aceita no maximo um: imagens, card ou citacao."
        )
    return presentes[0] if presentes else None


def pressao(slide: dict) -> float:
    """Quanto o slide ocupa do proprio orcamento. Acima de 1.0 encolhe todo mundo."""
    return len(slide.get("texto", "")) / ORCAMENTO_46[tipo_do_bloco(slide)]


# ── infra (nada aqui pode depender de arquivo fora da propria skill) ──────────

def _chave_no_env(env: Path, nome: str):
    """Le SOMENTE a chave pedida de um .env. Devolve o valor, ou None.

    A skill costuma ser instalada dentro do projeto de outra pessoa, e o .env
    desse projeto tende a estar cheio de credencial que nao tem nada a ver com
    carrossel. Nao ha motivo para carregar nada disso no processo.

    Le como utf-8-sig, nao utf-8: no Windows, Bloco de Notas e `Out-File
    -Encoding utf8` gravam BOM, e com utf-8 puro a primeira chave do arquivo
    vira "﻿KIE_API_KEY" e nunca casa com o nome. Falha invisivel, porque o
    arquivo parece perfeito em qualquer editor.
    """
    for linha in env.read_text(encoding="utf-8-sig").splitlines():
        if linha.lstrip().startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        if k.strip() != nome:
            continue
        v = v.strip().strip('"').strip("'")
        if v:                       # o .env.example tem a chave vazia
            return v
    return None


def carregar_chave(nome: str, onde_pegar: str) -> str:
    """Procura a chave no ambiente; se nao achar, varre .env subindo as pastas."""
    if os.environ.get(nome):
        return os.environ[nome]
    vistos = set()
    for partida in (Path(__file__).resolve().parent, Path.cwd()):
        for pasta in [partida, *partida.parents]:
            env = pasta / ".env"
            if env in vistos:
                continue
            vistos.add(env)
            if env.exists():
                chave = _chave_no_env(env, nome)
                if chave:
                    return chave
    # mensagem, nao traceback: o publico e criador de conteudo, e dez linhas de
    # stack lem como "quebrou", nao como "voce ainda precisa configurar"
    if sys.platform == "win32":
        cmd = f'  $env:{nome} = "sua-chave"'
    else:
        cmd = f'  export {nome}="sua-chave"'
    raise RuntimeError(
        f"Falta a chave {nome}. Pegue em {onde_pegar} e defina:\n\n{cmd}\n\n"
        f"Ou grave num arquivo .env como  {nome}=sua-chave"
    )


def _http(url, dados=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=dados, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        corpo = e.read()[:400].decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code} em {url}\n{corpo}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"nao consegui falar com {url}: {e.reason}") from None


def _http_json(url, payload=None, headers=None, timeout=60):
    headers = dict(headers or {})
    dados = None
    if payload is not None:
        dados = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    return json.loads(_http(url, dados, headers, timeout))


def tipo_imagem(b: bytes):
    """Identifica a imagem pelos bytes. None = nao e imagem."""
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:2] == b"\xff\xd8":
        return "jpg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def baixar_imagem(url: str, destino: Path) -> Path:
    """Baixa e confere os BYTES. Pagina de erro salva como .png e o jeito
    classico de "o arquivo existe" mentir."""
    b = _http(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    tipo = tipo_imagem(b)
    if not tipo:
        raise RuntimeError(
            f"o que veio de {url[:80]} nao e imagem ({len(b)} bytes). "
            "A URL pode ser de uma pagina, nao do arquivo."
        )
    destino = destino.with_suffix("." + tipo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b)
    return destino


def png_dimensoes(caminho: Path):
    """Largura e altura lidas do IHDR. None se nao for PNG."""
    b = Path(caminho).read_bytes()[:24]
    if b[:8] != b"\x89PNG\r\n\x1a\n" or b[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", b[16:24])


# ── kie.ai ────────────────────────────────────────────────────────────────────
#
# Endpoints fixados nos que ja foram validados em producao. getTaskDetail, que
# a skill instagram-post declara, devolve 404.

KIE_CRIAR = "https://api.kie.ai/api/v1/jobs/createTask"
KIE_STATUS = "https://api.kie.ai/api/v1/jobs/recordInfo"


def url_do_resultado(data: dict) -> str:
    """Extrai a URL de data.resultJson, que vem como STRING json aninhada."""
    out = data.get("resultJson")
    if isinstance(out, str):
        out = json.loads(out)
    urls = (out or {}).get("resultUrls") or (out or {}).get("result_urls") or []
    if not urls:
        raise RuntimeError(f"kie.ai terminou sem URL de resultado: {data}")
    return urls[0]


def gerar_imagem(prompt: str, destino: Path, aspect="1:1", modelo=KIE_MODELO):
    chave = carregar_chave("KIE_API_KEY", "https://kie.ai")
    h = {"Authorization": f"Bearer {chave}"}
    r = _http_json(KIE_CRIAR, {
        "model": modelo,
        "input": {"prompt": prompt, "aspect_ratio": aspect},
    }, h)
    if r.get("code") != 200 or not (r.get("data") or {}).get("taskId"):
        raise RuntimeError(f"kie.ai recusou a task: {r}")
    task = r["data"]["taskId"]
    print(f"kie.ai task {task} ...", flush=True)

    inicio, espera = time.time(), 4.0
    while True:
        decorrido = time.time() - inicio
        if decorrido > KIE_TIMEOUT:
            raise RuntimeError(
                f"kie.ai passou de {KIE_TIMEOUT // 60} min na task {task}. "
                "Confira os creditos em https://kie.ai e tente de novo."
            )
        d = _http_json(f"{KIE_STATUS}?taskId={urllib.parse.quote(task)}", None, h)
        d = d.get("data") or {}
        estado = d.get("state") or d.get("status")
        if estado == "success":
            return baixar_imagem(url_do_resultado(d), destino)
        if estado in ("fail", "failed", "error"):
            raise RuntimeError(f"kie.ai falhou: {d.get('failMsg') or d}")
        print(f"  {estado or 'na fila'} ({int(decorrido)}s)", flush=True)
        time.sleep(espera)
        espera = min(espera * 1.25, 15.0)


# ── Pexels ────────────────────────────────────────────────────────────────────

def buscar_stock(busca: str, destino: Path):
    chave = carregar_chave("PEXELS_API_KEY", "https://www.pexels.com/api/")
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": busca, "per_page": 1, "orientation": "landscape"})
    r = _http_json(url, None, {"Authorization": chave})
    fotos = r.get("photos") or []
    if not fotos:
        raise RuntimeError(f"Pexels nao achou nada para '{busca}'.")
    foto = fotos[0]
    print(f"Pexels: foto de {foto.get('photographer')} ({foto.get('url')})")
    return baixar_imagem(foto["src"]["large2x"], destino)


# ── HTML ──────────────────────────────────────────────────────────────────────
#
# Fonte de sistema de proposito. Google Fonts via CDN e aposta de corrida com o
# screenshot: se a fonte nao chegar a tempo o slide sai no fallback, sem erro
# nenhum e sem reproduzir na segunda tentativa.

MOLDE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>slide {n}</title>
<style>
  {fonte_embutida}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{L}px; height:{A}px; background:#fff;
                overflow:hidden; position:relative; }}
  body {{
    font-family:"Inter","Segoe UI",-apple-system,"Helvetica Neue",Arial,sans-serif;
    -webkit-font-smoothing:antialiased;
    letter-spacing:-0.01em;
  }}
  .emo {{ height:1.05em; width:1.05em; vertical-align:-0.19em;
          margin:0 .06em; display:inline-block; }}
  .slide {{ position:absolute; top:0; left:0; background:#fff;
            width:{L}px; height:{A}px; padding:{P}px; display:flex;
            flex-direction:column; overflow:hidden;
            visibility:hidden; }}          /* medidos, nao vistos */
  .slide.mostrar {{ visibility:visible; z-index:2; }}
  .ph {{ width:100%; border-radius:24px; background:#eee; }}
  .topo {{ display:flex; align-items:center; gap:22px; height:84px;
           flex:0 0 auto; margin-bottom:44px; }}
  .avatar {{ width:84px; height:84px; border-radius:50%; object-fit:cover;
             background:#cfd9de; flex:0 0 auto; }}
  .vazio {{ display:flex; align-items:center; justify-content:center;
            font-size:38px; font-weight:700; color:#fff; }}
  .nome {{ font-size:34px; font-weight:700; color:#0f1419; line-height:1.2; }}
  .arroba {{ font-size:32px; color:#536471; line-height:1.25; }}
  /* .corpo e a caixa que mede; .miolo e o conteudo, centralizado nela.
     A medida e miolo.offsetHeight vs corpo.clientHeight, nao scrollHeight:
     com flex centralizado o conteudo que nao cabe escapa pelos DOIS lados e o
     scrollHeight deixa de contar o que subiu acima do topo. */
  .corpo {{ flex:1 1 auto; min-height:0; overflow:hidden;
            display:flex; flex-direction:column; }}
  /* Centralizacao OPTICA: a sobra vai 1/3 em cima e 2/3 embaixo.
     Centralizar de verdade (justify-content:center) abre um buraco entre o
     cabecalho e o texto que a referencia nao tem - o nome e o texto precisam
     parecer grudados. Deixar tudo no topo joga a sobra toda embaixo, que foi
     a reclamacao original. 1:2 resolve os dois. */
  .corpo::before {{ content:''; flex:1 1 0; }}
  .corpo::after  {{ content:''; flex:2 1 0; }}
  .miolo {{ flex:0 0 auto; }}
  .texto {{ font-size:{fonte}px; line-height:{lh}; color:#0f1419;
            white-space:pre-wrap; word-wrap:break-word; }}
  .texto p + p {{ margin-top:{gap}px; }}
  .bloco {{ margin-top:36px; }}
  .fotos {{ display:flex; gap:24px; }}
  .fotos img {{ width:100%; height:464px; object-fit:cover; border-radius:24px;
                border:1px solid #cfd9de; }}
  .fotos.uma img {{ height:540px; }}
  .card {{ border:1px solid #cfd9de; border-radius:24px; overflow:hidden; }}
  .card .marca {{ display:flex; align-items:center; gap:26px; padding:20px 30px;
                  background:var(--cor); }}
  .card .fonte {{ font-size:38px; font-weight:800; color:#fff;
                  letter-spacing:-1px; }}
  .card .chapeu {{ font-size:24px; color:rgba(255,255,255,.9);
                   letter-spacing:2px; }}
  .card .miolo {{ padding:30px; }}
  .card h2 {{ font-size:42px; font-weight:700; color:#0f1419; line-height:1.2; }}
  .card .linha {{ font-size:27px; color:#536471; line-height:1.4;
                  margin-top:18px; }}
  .citacao {{ background:#f7f9f9; border-radius:20px; padding:34px 38px;
              font-size:30px; line-height:1.45; color:#0f1419;
              white-space:pre-wrap; }}
  mark {{ background:#fff08a; color:#0f1419; padding:2px 0; }}
  .estouro {{ position:absolute; top:0; left:0; width:{L}px; padding:20px;
              background:#d62828; color:#fff; font-size:34px; font-weight:700;
              text-align:center; z-index:9; }}
</style></head><body>
{slides}
<script>
  // O tamanho do corpo do texto e UM SO para o carrossel inteiro: o maior em
  // que TODOS os slides cabem. Todas as paginas medem o mesmo conjunto e
  // chegam sozinhas na mesma resposta.
  (function () {{
    var slides = [].slice.call(document.querySelectorAll('.slide'));
    function cabe(s) {{
      // miolo vs corpo, nao scrollHeight: com o conteudo centralizado o que
      // nao cabe escapa pelos DOIS lados, e o scrollHeight perde o pedaco que
      // subiu acima do topo - a barra de estouro deixaria de aparecer.
      return s.querySelector('.miolo').offsetHeight <=
             s.querySelector('.corpo').clientHeight;
    }}
    function aplicar(f) {{
      slides.forEach(function (s) {{
        s.querySelector('.texto').style.fontSize = f + 'px';
      }});
      return slides.every(cabe);
    }}
    var f = {fonte};
    while (f > {piso} && !aplicar(f)) f -= 1;
    aplicar(f);

    // Se o slide visivel ainda estoura na fonte minima, o defeito vai no PNG:
    // um preview com barra vermelha e impossivel de postar sem ver.
    if (!cabe(document.querySelector('.slide.mostrar'))) {{
      document.body.insertAdjacentHTML('beforeend',
        '<div class="estouro">TEXTO NAO COUBE \\u2014 encurte o slide {n}</div>');
    }}
  }})();
</script>
</body></html>
"""

SLIDE = """<div class="slide{mostrar}">
  <div class="topo">{avatar}
    <div><div class="nome">{nome}</div><div class="arroba">{arroba}</div></div>
  </div>
  <div class="corpo"><div class="miolo">
    <div class="texto">{texto}</div>
    {bloco}
  </div></div>
</div>"""


def _paragrafos(texto: str, cache: Path) -> str:
    blocos = [p for p in texto.split("\n\n") if p.strip()]
    return "".join(
        "<p>" + trocar_emoji(
            html.escape(p.strip()).replace("\n", "<br>"), cache) + "</p>"
        for p in blocos
    )


def _uri(caminho: Path) -> str:
    return caminho.resolve().as_uri()


def _bloco_html(slide: dict, tipo, base: Path, real=True) -> str:
    """`real=False` troca as fotos por um placeholder da MESMA altura.

    As copias escondidas existem so para medir. A altura das fotos e fixa no
    CSS, entao um div vazio ocupa exatamente o mesmo espaco, sem pagar N
    decodificacoes de imagem por pagina.
    """
    if tipo == "imagens":
        caminhos = [base / p for p in slide["imagens"]][:2]
        for c in caminhos:
            if not c.exists():
                raise RuntimeError(f"imagem do spec nao existe: {c}")
        uma = " uma" if len(caminhos) == 1 else ""
        altura = 540 if len(caminhos) == 1 else 464
        if real:
            miolo = "".join(f'<img src="{_uri(c)}">' for c in caminhos)
        else:
            miolo = f'<div class="ph" style="height:{altura}px"></div>' * len(caminhos)
        return f'<div class="bloco"><div class="fotos{uma}">{miolo}</div></div>'

    if tipo == "card":
        c = slide["card"]
        linha = c.get("texto", "")
        return (
            f'<div class="bloco"><div class="card" '
            f'style="--cor:{html.escape(c.get("cor", "#c4170c"))}">'
            f'<div class="marca"><span class="fonte">'
            f'{html.escape(c.get("fonte", ""))}</span>'
            f'<span class="chapeu">{html.escape(c.get("chapeu", ""))}</span></div>'
            f'<div class="miolo"><h2>{html.escape(c.get("titulo", ""))}</h2>'
            + (f'<div class="linha">{html.escape(linha)}</div>' if linha else "")
            + "</div></div></div>"
        )

    if tipo == "citacao":
        c = slide["citacao"]
        corpo = html.escape(c.get("texto", ""))
        destaque = c.get("destaque")
        if destaque:
            alvo = html.escape(destaque)
            if alvo not in corpo:
                raise RuntimeError(
                    f"o destaque '{destaque}' nao aparece no texto da citacao"
                )
            corpo = corpo.replace(alvo, f"<mark>{alvo}</mark>", 1)
        return f'<div class="bloco"><div class="citacao">{corpo}</div></div>'

    return ""


def html_da_pagina(perfil: dict, slides: list, n: int, base: Path,
                   cache: Path = None) -> str:
    """Pagina do slide `n` (1-based), com todos os outros junto para medir."""
    cache = cache or (base / "emoji")
    avatar_path = perfil.get("avatar")
    if avatar_path and (base / avatar_path).exists():   # Path absoluto tambem
        avatar = f'<img class="avatar" src="{_uri(base / avatar_path)}">'
    else:
        inicial = html.escape((perfil.get("nome") or "?")[:1].upper())
        avatar = f'<div class="avatar vazio">{inicial}</div>'

    marcacao = []
    for i, slide in enumerate(slides, 1):
        texto = slide.get("texto", "").strip()
        if not texto:
            raise RuntimeError(f"slide {i} esta sem texto")
        visivel = i == n
        marcacao.append(SLIDE.format(
            mostrar=" mostrar" if visivel else "",
            avatar=avatar,
            nome=html.escape(perfil.get("nome", "")),
            arroba=html.escape(perfil.get("arroba", "")),
            texto=_paragrafos(texto, cache),
            bloco=_bloco_html(slide, tipo_do_bloco(slide), base, real=visivel),
        ))

    return MOLDE.format(
        n=n, L=LARGURA, A=ALTURA, P=PADDING,
        fonte=FONTE_BASE, piso=FONTE_PISO, lh=ENTRELINHA, gap=GAP_PARAGRAFO,
        fonte_embutida=_fonte_embutida(),
        slides="\n".join(marcacao),
    )


# ── browser ───────────────────────────────────────────────────────────────────

def achar_browser() -> str:
    pf, pf86 = os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")
    local = os.environ.get("LOCALAPPDATA", "")
    candidatos = {
        "win32": [
            rf"{pf}\Google\Chrome\Application\chrome.exe",
            rf"{pf86}\Google\Chrome\Application\chrome.exe",
            rf"{local}\Google\Chrome\Application\chrome.exe",
            rf"{pf}\Microsoft\Edge\Application\msedge.exe",
            rf"{pf86}\Microsoft\Edge\Application\msedge.exe",
        ],
        "darwin": [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ],
    }.get(sys.platform, [])

    for c in candidatos:
        if c and Path(c).exists():
            return c
    for nome in ("google-chrome", "chromium", "chromium-browser",
                 "microsoft-edge", "chrome"):
        achado = shutil.which(nome)
        if achado:
            return achado

    instalar = {
        "win32": "  winget install Google.Chrome",
        "darwin": "  brew install --cask google-chrome",
    }.get(sys.platform, "  sudo apt install chromium-browser")
    raise RuntimeError(
        "nao achei Chrome nem Edge para renderizar os slides. Instale:\n\n"
        + instalar
    )


def screenshot(browser: str, pagina: Path, png: Path, perfil_tmp: str):
    subprocess.run([
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--user-data-dir={perfil_tmp}",       # nao briga com um Chrome aberto
        "--force-device-scale-factor=1",
        f"--window-size={LARGURA},{ALTURA}",
        "--virtual-time-budget=3000",          # deixa o JS de ajuste rodar
        f"--screenshot={png}",
        pagina.resolve().as_uri(),
    ], check=False, capture_output=True, timeout=120)


PREVIEW = """<!doctype html><meta charset="utf-8"><title>carrossel</title>
<style>body{{background:#111;color:#eee;font:15px system-ui;padding:28px}}
.g{{display:flex;flex-wrap:wrap;gap:18px;margin-top:18px}}
figure{{margin:0}}img{{width:300px;border-radius:10px;display:block}}
figcaption{{text-align:center;padding-top:6px;color:#999}}</style>
<h1>{titulo}</h1><p>{n} slides &middot; 1080&times;1350</p><div class="g">{itens}</div>
"""


# ── montar ────────────────────────────────────────────────────────────────────

def achar_config(base: Path):
    """config.json com nome, arroba e avatar. Procura ao lado do spec e depois
    nas pastas acima, entao um config na raiz dos carrosseis serve para todos.

    O que o spec traz em `perfil` ganha do config - carrossel de cliente nao
    precisa de arquivo novo, e so sobrescrever no proprio spec.
    """
    for pasta in [base, *base.parents][:4]:
        cfg = pasta / "config.json"
        if not cfg.exists():
            continue
        dados = json.loads(cfg.read_text(encoding="utf-8-sig"))
        dados = dict(dados.get("perfil", dados))
        # o avatar do config e relativo A PASTA DO CONFIG, que nem sempre e a
        # do spec - vira absoluto aqui para nao apontar pro lugar errado
        if dados.get("avatar"):
            dados["avatar"] = str((pasta / dados["avatar"]).resolve())
        return dados, cfg
    return {}, None


def montar(spec_path: Path, saida: Path):
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    base = spec_path.resolve().parent

    config, de_onde = achar_config(base)
    perfil = {**config, **(spec.get("perfil") or {})}
    perfil = {k: v for k, v in perfil.items()
              if k in ("nome", "arroba", "avatar") and v}
    if de_onde:
        print(f"perfil: {de_onde}")
    faltando = [c for c in ("nome", "arroba") if not perfil.get(c)]
    if faltando:
        raise RuntimeError(
            f"falta {' e '.join(faltando)} no perfil. Crie um config.json em "
            f"{base} (ou numa pasta acima) assim:\n\n"
            '  {"nome": "Seu Nome", "arroba": "@seuusuario",\n'
            '   "avatar": "perfil.jpg"}'
        )

    slides = spec.get("slides") or []
    if not slides:
        raise RuntimeError("o spec nao tem slides")
    # Recusa so se ja houver carrossel RENDERIZADO ali. "Pasta nao vazia" era
    # cedo demais: o spec.json e a pasta img/ moram dentro do proprio <OUT>,
    # que e o layout que o SKILL.md manda usar - entao a primeira renderizacao
    # de todo carrossel batia na trava.
    pronto = sorted(saida.glob("slide-*.png")) if saida.exists() else []
    if pronto:
        raise RuntimeError(
            f"{saida} ja tem {len(pronto)} slide(s) renderizado(s). Apague-os "
            "ou escolha outra pasta para nao sobrescrever um carrossel pronto."
        )

    # Um slide longo demais encolhe o carrossel inteiro, e o browser aplica
    # isso calado. Aqui o culpado tem nome antes do render comecar.
    apertados = [(i, s) for i, s in enumerate(slides, 1) if pressao(s) > 1.0]
    for i, s in sorted(apertados, key=lambda x: -pressao(x[1])):
        orcamento = ORCAMENTO_46[tipo_do_bloco(s)]
        print(f"aviso: o slide {i} tem {len(s['texto'])} caracteres para um "
              f"orcamento de {orcamento}. Ele encolhe a fonte de TODOS os "
              f"slides. Encurte para o carrossel ficar em {FONTE_BASE}px.")

    browser = achar_browser()
    saida.mkdir(parents=True, exist_ok=True)
    paginas = saida / "html"
    paginas.mkdir(exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="carousel-chrome-")
    pngs = []
    try:
        for i in range(1, len(slides) + 1):
            pagina = paginas / f"slide-{i:02d}.html"
            pagina.write_text(html_da_pagina(perfil, slides, i, base),
                              encoding="utf-8")
            png = saida / f"slide-{i:02d}.png"
            screenshot(browser, pagina, png, tmp)
            pngs.append(png)
            print(f"  slide {i:02d} ok", flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # sondar o artefato entregue. Nenhum numero daqui vem de parametro.
    problemas = []
    for png in pngs:
        if not png.exists() or png.stat().st_size < 2000:
            problemas.append(f"{png.name}: nao foi gerado")
            continue
        dim = png_dimensoes(png)
        if dim != (LARGURA, ALTURA):
            problemas.append(f"{png.name}: saiu {dim}, esperado "
                             f"({LARGURA}, {ALTURA})")
    if problemas:
        raise RuntimeError("o render nao fechou:\n  " + "\n  ".join(problemas))

    itens = "".join(
        f'<figure><img src="{p.name}"><figcaption>{p.name}</figcaption></figure>'
        for p in pngs
    )
    preview = saida / "preview.html"
    preview.write_text(
        PREVIEW.format(titulo=spec.get("titulo", "Carrossel"),
                       n=len(pngs), itens=itens),
        encoding="utf-8")

    print(f"\n{len(pngs)} slides em {saida}")
    print(f"preview: {preview}")
    print("confira se algum slide saiu com a barra vermelha de estouro.")
    return pngs


# ── autoteste ─────────────────────────────────────────────────────────────────
#
# So o que e mecanico. Os slides abaixo sao o texto REAL do carrossel de
# referencia: se alguem mexer no canvas, na fonte ou na estimativa e a copia de
# referencia parar de caber, o teste cai.

SLIDE_LISTA = (
    "✅ Entre as mudanças pedidas estão coisas como:\n\n"
    "→ acabar com o scroll infinito\n"
    "→ remover número de curtidas\n"
    "→ limitar o tempo de uso de jovens\n"
    "→ aumentar as restrições pra menores de 13 anos\n\n"
    "Ou seja:\n\n"
    "eles estão atacando o design do produto, não apenas a Meta "
    "como empresa."
)
SLIDE_GANCHO = (
    "\U0001f6a8AGORA: O Instagram pode ser forçado a retirar os Reels por "
    "causa de um processo de até US$ 1,4 TRILHÃO.\n\n"
    "Vou te atualizar sobre o que tá acontecendo \U0001f449"
)
SLIDE_CARD = (
    "Mark Zuckerberg e a Meta estão no meio de um dos julgamentos mais "
    "importantes da história das redes sociais.\n\n"
    "29 estados americanos acusam a empresa de ter desenvolvido Instagram e "
    "Facebook de maneira propositalmente viciante para usuários mais "
    "jovens ⚠️\n\n"
    "E qual foi a acusação?\U0001f449"
)


def autoteste():
    # Nao ha assert de "cabe" aqui de proposito: quem mede e o browser, dentro
    # da pagina. Testar a estimativa em Python era testar a ficcao que foi
    # apagada. O que da para prender e a MARCACAO que o browser recebe, e o
    # orcamento, que foi medido no Chrome.

    # ── pressao: os slides reais da referencia cabem a 46px ─────────────────
    assert pressao({"texto": SLIDE_LISTA}) < 1.0, pressao({"texto": SLIDE_LISTA})
    assert pressao({"texto": SLIDE_GANCHO, "imagens": ["a", "b"]}) < 1.0
    assert pressao({"texto": SLIDE_CARD, "card": {"fonte": "g1"}}) < 1.0

    # o caso real que derrubou o carrossel de 46px para 30px no primeiro teste
    monstro = {"texto": "Slide proposital de estouro. " * 60}
    assert len(monstro["texto"]) == 1740
    assert pressao(monstro) > 2.5, pressao(monstro)

    # o mesmo texto com foto aperta mais do que sem: foto rouba espaco
    assert pressao({"texto": SLIDE_LISTA, "imagens": ["a"]}) > \
           pressao({"texto": SLIDE_LISTA})

    # piso alto o bastante para que um slide gigante NAO arraste os outros
    assert FONTE_PISO >= 36, "abaixo de 36px o paredao de texto volta a passar"

    # ── emoji do Twitter, nao o do Windows ──────────────────────────────────
    assert codigo_twemoji("\U0001f6a8") == "1f6a8"          # sirene
    assert codigo_twemoji("⚠️") == "26a0"         # aviso: tira FE0F
    assert codigo_twemoji("➡️") == "27a1"         # seta
    assert codigo_twemoji("\U0001f449") == "1f449"
    # com ZWJ o FE0F FICA - e a regra do proprio Twemoji
    assert codigo_twemoji("\U0001f468‍\U0001f4bb") == "1f468-200d-1f4bb"

    achados = EMOJI.findall("\U0001f6a8AGORA: o Google… vou explicar \U0001f449")
    assert achados == ["\U0001f6a8", "\U0001f449"], achados
    # a seta "→" das listas e TEXTO, nao emoji: o Twemoji nao tem arquivo dela
    assert EMOJI.findall("→ acabar com o scroll infinito") == []
    assert EMOJI.findall("US$ 40 bi, 5 GW, 100% — nada disso e emoji") == []

    # os emoji do vocabulario da skill vieram junto: funcionam sem rede
    faltando = [c for c in ("1f6a8", "26a0", "2705", "27a1", "1f449")
                if not (ASSETS / "emoji" / f"{c}.png").exists()]
    assert not faltando, f"emoji embarcado sumiu: {faltando}"

    # ── a fonte vai embutida: mesmo render em qualquer maquina ──────────────
    css = _fonte_embutida()
    assert "data:font/woff2;base64," in css, "a Inter nao foi embutida"
    assert css.count("@font-face") == 2, "faltou peso da Inter"

    # ── um bloco por slide, nem mais ────────────────────────────────────────
    assert tipo_do_bloco({"texto": "x"}) is None
    assert tipo_do_bloco({"texto": "x", "imagens": ["a.jpg"]}) == "imagens"
    assert tipo_do_bloco({"texto": "x", "imagens": []}) is None
    try:
        tipo_do_bloco({"texto": "x", "imagens": ["a"], "card": {"fonte": "g1"}})
        raise AssertionError("dois blocos no mesmo slide tinha que estourar")
    except RuntimeError:
        pass

    # ── kie.ai: resultJson vem como STRING json aninhada ────────────────────
    assert url_do_resultado({
        "state": "success",
        "resultJson": '{"resultUrls":["https://cdn.kie.ai/a.png"]}',
    }) == "https://cdn.kie.ai/a.png"
    assert url_do_resultado({
        "resultJson": {"resultUrls": ["https://cdn.kie.ai/b.png"]},
    }) == "https://cdn.kie.ai/b.png"
    try:
        url_do_resultado({"resultJson": '{"resultUrls":[]}'})
        raise AssertionError("success sem URL tinha que estourar")
    except RuntimeError:
        pass

    # ── bytes, nao extensao: e o que separa imagem de pagina de erro ────────
    assert tipo_imagem(b"\x89PNG\r\n\x1a\n" + b"\0" * 8) == "png"
    assert tipo_imagem(b"\xff\xd8\xff\xe0") == "jpg"
    assert tipo_imagem(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert tipo_imagem(b"<!doctype html><title>404") is None

    tmpdir = Path(tempfile.mkdtemp(prefix="carousel-teste-"))
    try:
        # ── IHDR: o numero reportado tem que sair do arquivo ────────────────
        ihdr = struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1080, 1350)
        png = tmpdir / "f.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + b"\x08\x06\x00\x00\x00")
        assert png_dimensoes(png) == (1080, 1350), png_dimensoes(png)
        nao = tmpdir / "n.png"
        nao.write_bytes(b"<html>")
        assert png_dimensoes(nao) is None

        # ── BOM: o que Bloco de Notas e `Out-File -Encoding utf8` gravam ────
        env = tmpdir / ".env"
        env.write_text("KIE_API_KEY=kie-com-bom\nOPENAI_API_KEY=vizinha\n",
                       encoding="utf-8-sig")
        assert env.read_bytes().startswith(b"\xef\xbb\xbf"), "o teste precisa do BOM"
        assert _chave_no_env(env, "KIE_API_KEY") == "kie-com-bom"
        # a credencial do lado nao pode vazar para o processo
        assert "OPENAI_API_KEY" not in os.environ or \
               os.environ["OPENAI_API_KEY"] != "vizinha"
        assert _chave_no_env(env, "PEXELS_API_KEY") is None

        # ── HTML: escape, paragrafos e o destaque amarelo ───────────────────
        # ── config.json: o spec ganha do config, e o avatar resolve na pasta
        #    DO CONFIG, que nem sempre e a do spec ──────────────────────────
        raiz = tmpdir / "carrosseis"
        (raiz / "um").mkdir(parents=True)
        (raiz / "rosto.jpg").write_bytes(b"\xff\xd8")
        (raiz / "config.json").write_text(json.dumps(
            {"nome": "Anderson", "arroba": "@andr", "avatar": "rosto.jpg"}),
            encoding="utf-8")
        cfg, onde = achar_config(raiz / "um")
        assert onde == raiz / "config.json", onde       # achou subindo a pasta
        assert Path(cfg["avatar"]) == (raiz / "rosto.jpg").resolve(), cfg
        assert cfg["nome"] == "Anderson"
        # tambem aceita o formato aninhado {"perfil": {...}}
        (raiz / "um" / "config.json").write_text(
            json.dumps({"perfil": {"nome": "Outro", "arroba": "@o"}}),
            encoding="utf-8")
        assert achar_config(raiz / "um")[0]["nome"] == "Outro"
        assert achar_config(tmpdir / "sem-nada") == ({}, None)

        perfil = {"nome": "Fulano <b>", "arroba": "@fulano"}
        so_um = [{"texto": SLIDE_GANCHO}]
        pagina = html_da_pagina(perfil, so_um, 1, tmpdir)
        assert "Fulano &lt;b&gt;" in pagina, "nome tem que ser escapado"
        assert pagina.count("<p>") == 2, "dois paragrafos no slide do gancho"
        assert 'class="avatar vazio"' in pagina, "sem avatar, cai no fallback"
        assert "TEXTO NAO COUBE" in pagina, "a barra de estouro sumiu do molde"

        # ── o spec e as imagens moram no <OUT> e NAO contam como "ja pronto" ─
        # Primeiro carrossel de verdade morreu aqui: a trava olhava "pasta nao
        # vazia" e o proprio spec.json ja tornava a pasta nao vazia.
        saida = tmpdir / "saida"
        (saida / "img").mkdir(parents=True)
        (saida / "spec.json").write_text("{}", encoding="utf-8")
        (saida / "img" / "a.jpg").write_bytes(b"\xff\xd8")
        assert not sorted(saida.glob("slide-*.png")), "spec/img nao sao slides"
        (saida / "slide-01.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        assert sorted(saida.glob("slide-*.png")), "slide pronto tem que contar"

        # ── a pagina carrega TODOS os slides: e assim que a fonte sai igual ──
        # em todo o carrossel. Se alguem "otimizar" isso, cada slide volta a
        # ter um tamanho de fonte proprio e o carrossel fica desalinhado.
        (tmpdir / "foto.jpg").write_bytes(b"\xff\xd8\xff\xe0")
        tres = [{"texto": SLIDE_GANCHO, "imagens": ["foto.jpg"]},
                {"texto": SLIDE_CARD},
                {"texto": SLIDE_LISTA}]
        p2 = html_da_pagina(perfil, tres, 2, tmpdir)
        assert p2.count('class="slide') == 3, "faltou slide para medir"
        assert p2.count('class="slide mostrar"') == 1, "um e so um visivel"
        assert 'class="slide mostrar"' in html_da_pagina(perfil, tres, 3, tmpdir)
        # so o visivel carrega a imagem de verdade; os outros usam placeholder
        p1 = html_da_pagina(perfil, tres, 1, tmpdir)
        assert p1.count("<img src=") == 1 and "ph" in p2, "placeholder sumiu"
        assert "<img src=" not in p2, "slide escondido nao decodifica imagem"
        assert 'style="height:540px"' in p2, "placeholder com altura errada"

        citado = html_da_pagina(perfil, [{
            "texto": "x",
            "citacao": {"texto": 'muda o "algoritmo" dela', "destaque": '"algoritmo"'},
        }], 1, tmpdir)
        assert "<mark>&quot;algoritmo&quot;</mark>" in citado, citado[-400:]
        for ruim, porque in [
            ({"texto": "x", "citacao": {"texto": "abc", "destaque": "nao ta ai"}},
             "destaque fora do texto"),
            ({"texto": "   "}, "slide sem texto"),
            ({"texto": "x", "imagens": ["sumiu.jpg"]}, "imagem inexistente"),
        ]:
            try:
                html_da_pagina(perfil, [ruim], 1, tmpdir)
                raise AssertionError(f"{porque} tinha que estourar")
            except RuntimeError:
                pass
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("✅ autoteste passou")


# ── cli ───────────────────────────────────────────────────────────────────────

def _opcao(args, nome, padrao=None):
    return args[args.index(nome) + 1] if nome in args else padrao


def main():
    args = sys.argv[1:]
    if "--autoteste" in args:
        autoteste()
        return
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd, resto = args[0], args[1:]
    saida = _opcao(resto, "--out")
    livres = [a for a in resto if not a.startswith("--")]
    if saida in livres:
        livres.remove(saida)

    if cmd == "montar":
        if not livres or not saida:
            raise RuntimeError("uso: montar <spec.json> --out <pasta>")
        montar(Path(livres[0]), Path(saida))
    elif cmd == "imagem":
        if not livres or not saida:
            raise RuntimeError('uso: imagem "<prompt>" --out <arquivo.png>')
        p = gerar_imagem(livres[0], Path(saida), _opcao(resto, "--aspect", "1:1"),
                         _opcao(resto, "--modelo", KIE_MODELO))
        print(p)
    elif cmd == "stock":
        if not livres or not saida:
            raise RuntimeError('uso: stock "<busca>" --out <arquivo.png>')
        print(buscar_stock(livres[0], Path(saida)))
    elif cmd == "baixar":
        if not livres or not saida:
            raise RuntimeError("uso: baixar <url> --out <arquivo.png>")
        print(baixar_imagem(livres[0], Path(saida)))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
