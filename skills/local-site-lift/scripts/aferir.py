#!/usr/bin/env python3
"""
aferir.py - mede o artesanato do site entregue, em numeros.

  aferir.py dist/            confere e lista o que esta abaixo do chao
  aferir.py --autoteste

Existe porque `design-floor.md` era so uma lista de proibicoes. Ele ensinava o
que EVITAR e nunca o que ATINGIR, entao um agente jogava seguro e entregava
site plano, sem contraste e com metade da tela vazia. Aconteceu duas vezes.

Contencao vira vazio quando ninguem mede o resultado. Estes numeros sao o chao,
nao a meta: bater todos nao faz um site bonito, mas falhar em qualquer um faz
um site que parece barato.

Cada limite saiu de um site real que ficou ruim, e o comentario diz qual.
"""

import argparse
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# O h1 de um site institucional tem que dominar a primeira tela. 2.5rem num
# monitor de 1440 le como subtitulo, e foi o que saiu no site da Stella.
H1_MINIMO_REM = 3.0
RAZAO_MINIMA = 2.6          # h1 / corpo. Abaixo disso nao existe hierarquia

# 10 tamanhos com 7 amontoados entre 0.85 e 1.15rem nao e escala, e ruido.
TAMANHOS_MAXIMO = 8
DEGRAU_MINIMO = 1.12        # dois tamanhos a 3% de distancia nao se distinguem

# 1 transicao e 1 sombra em 75 regras: nada responde ao cursor, nada tem
# profundidade. O site fica com cara de rascunho de HTML.
HOVER_MINIMO = 4
TRANSICAO_MINIMA = 3

# h1 { max-width: 18ch } foi o defeito central do site da Stella: o titulo
# quebrava em tres linhas curtas e metade da tela ficava vazia.
CH_MINIMO_TITULO = 24


class Erro(RuntimeError):
    pass


def _rem(valor: str):
    """'2.5rem' | '40px' | '1.05em' -> float em rem (16px = 1rem)."""
    m = re.match(r"^\s*([\d.]+)\s*(rem|em|px)\s*$", valor or "")
    if not m:
        return None
    n = float(m.group(1))
    return n / 16 if m.group(2) == "px" else n


def tamanhos_de_fonte(css: str) -> list:
    achados = []
    for m in re.finditer(r"font-size:\s*([^;}\n]+)", css):
        r = _rem(m.group(1))
        if r:
            achados.append(round(r, 3))
    return sorted(set(achados))


def fonte_do_seletor(css: str, seletor: str):
    """Maior font-size declarado para um seletor. Media query costuma subir o
    h1 no desktop, e e esse o valor que vale."""
    maior = None
    for m in re.finditer(re.escape(seletor) + r"[^{}]*\{([^}]*)\}", css):
        for f in re.finditer(r"font-size:\s*([^;}\n]+)", m.group(1)):
            r = _rem(f.group(1))
            if r and (maior is None or r > maior):
                maior = r
    return maior


def largura_em_ch(css: str, seletor: str):
    """max-width em `ch` de um seletor. `h1 { max-width: 18ch }` estrangula."""
    menor = None
    for m in re.finditer(re.escape(seletor) + r"[^{}]*\{([^}]*)\}", css):
        for w in re.finditer(r"max-width:\s*([\d.]+)ch", m.group(1)):
            v = float(w.group(1))
            if menor is None or v < menor:
                menor = v
    return menor


def _bloco_media(css: str, inicio: int) -> str:
    """Conteudo de um @media, contando chaves. Regex nao serve: o bloco tem
    chaves aninhadas, e casar ate a primeira '}' ou ate '\\n}' erra dos dois
    jeitos, dependendo de como o CSS foi formatado."""
    i = css.find("{", inicio)
    if i == -1:
        return ""
    nivel, j = 0, i
    while j < len(css):
        if css[j] == "{":
            nivel += 1
        elif css[j] == "}":
            nivel -= 1
            if nivel == 0:
                return css[i + 1:j]
        j += 1
    return css[i + 1:]


def grades_no_desktop(css: str) -> int:
    """Quantos `grid-template-columns` de VARIAS colunas existem dentro de
    media query. Sem isso o desktop e a coluna do celular esticada."""
    n = 0
    for m in re.finditer(r"@media", css):
        dentro = _bloco_media(css, m.end())
        for g in re.finditer(r"grid-template-columns:\s*([^;}\n]+)", dentro):
            v = g.group(1).strip()
            if "repeat" in v or len(v.split()) > 1:
                n += 1
    return n


def medir(dist: Path) -> dict:
    index = dist / "index.html"
    if not index.exists():
        raise Erro(f"nao achei {index}")
    html = index.read_text(encoding="utf-8", errors="replace")
    css = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                    for p in sorted(dist.rglob("*.css")))
    css += "\n" + "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))

    tamanhos = tamanhos_de_fonte(css)
    h1 = fonte_do_seletor(css, "h1")
    corpo = fonte_do_seletor(css, "body") or 1.0
    # degraus colados: dois tamanhos que ninguem distingue
    colados = sum(1 for a, b in zip(tamanhos, tamanhos[1:])
                  if b / a < DEGRAU_MINIMO)
    return {
        "h1_rem": h1,
        "corpo_rem": corpo,
        "razao": round(h1 / corpo, 2) if h1 and corpo else None,
        "tamanhos": tamanhos,
        "colados": colados,
        "h1_ch": largura_em_ch(css, "h1"),
        "hover": len(re.findall(r":hover", css)),
        "focus": len(re.findall(r":focus", css)),
        "transicao": len(re.findall(r"transition", css)),
        "grades_desktop": grades_no_desktop(css),
        "media_queries": len(re.findall(r"@media", css)),
        "footer": "<footer" in html,
        "regras": css.count("{"),
    }


def avaliar(m: dict) -> list:
    """Lista de falhas. Cada uma diz o numero medido e o que se espera."""
    f = []
    if not m["h1_rem"]:
        f.append("o h1 nao tem font-size declarado")
    elif m["h1_rem"] < H1_MINIMO_REM:
        f.append(f"h1 em {m['h1_rem']}rem. No desktop um titulo institucional "
                 f"precisa de pelo menos {H1_MINIMO_REM}rem, ou le como subtitulo")
    if m["razao"] and m["razao"] < RAZAO_MINIMA:
        f.append(f"h1 tem so {m['razao']}x o corpo do texto. Abaixo de "
                 f"{RAZAO_MINIMA}x nao existe hierarquia, so tamanhos parecidos")
    if len(m["tamanhos"]) > TAMANHOS_MAXIMO:
        f.append(f"{len(m['tamanhos'])} tamanhos de fonte diferentes. Acima de "
                 f"{TAMANHOS_MAXIMO} nao e escala, e ruido: {m['tamanhos']}")
    if m["colados"]:
        f.append(f"{m['colados']} par(es) de tamanhos a menos de "
                 f"{int((DEGRAU_MINIMO-1)*100)}% de distancia. Ninguem "
                 "distingue, entao nao comunicam nada")
    if m["h1_ch"] and m["h1_ch"] < CH_MINIMO_TITULO:
        f.append(f"h1 com max-width de {int(m['h1_ch'])}ch. Isso estrangula o "
                 "titulo em linhas curtas e deixa a tela vazia ao lado")
    if m["hover"] < HOVER_MINIMO:
        f.append(f"{m['hover']} estado(s) :hover em {m['regras']} regras. Nada "
                 "responde ao cursor, e o site parece um rascunho")
    if not m["focus"]:
        f.append("nenhum estado de foco: quem navega por teclado fica perdido")
    if m["transicao"] < TRANSICAO_MINIMA:
        f.append(f"{m['transicao']} transicao(oes). Sem elas todo estado troca "
                 "seco, e isso e o que mais denuncia site amador")
    if m["media_queries"] and not m["grades_desktop"]:
        f.append("nenhuma grade de varias colunas no desktop. O layout largo "
                 "vira a coluna do celular esticada, com metade da tela vazia")
    if not m["footer"]:
        f.append("sem <footer>: o site termina no ar e parece inacabado")
    return f


def relatar(dist: Path) -> int:
    m = medir(dist)
    print(f"\n{dist}")
    print(f"  h1 {m['h1_rem']}rem  corpo {m['corpo_rem']}rem  razao {m['razao']}x")
    print(f"  {len(m['tamanhos'])} tamanhos  |  hover {m['hover']}  focus "
          f"{m['focus']}  transicao {m['transicao']}")
    print(f"  {m['grades_desktop']} grade(s) no desktop  |  footer: "
          f"{'sim' if m['footer'] else 'NAO'}")
    falhas = avaliar(m)
    if not falhas:
        print("\n  ✅ passa no chao de artesanato")
        return 0
    print(f"\n  {len(falhas)} ponto(s) abaixo do chao:\n")
    for x in falhas:
        print(f"   ❌ {x}")
    print("\nIsto e o chao, nao a meta. Passar nao garante um site bonito;")
    print("falhar garante um site que parece barato.")
    return 1


def autoteste():
    # ── o site real que motivou o script, com os numeros dele ───────────────
    ruim = """
    body { font-size: 1rem; }
    h1 { max-width: 18ch; }
    p { max-width: 68ch; }
    .a { font-size: 0.85rem; } .b { font-size: 0.9rem; } .c { font-size: 0.95rem; }
    .d { font-size: 1.05rem; } .e { font-size: 1.1rem; } .f { font-size: 1.15rem; }
    .g { font-size: 1.6rem; } .h { font-size: 1.9rem; }
    .btn:hover { opacity: .9; } a:hover { color: red; }
    .x { transition: all .2s; } .y:focus { outline: 1px; }
    @media (min-width: 900px) { .hero h1 { font-size: 2.5rem; } }
    """
    assert _rem("2.5rem") == 2.5 and _rem("40px") == 2.5 and _rem("x") is None
    assert fonte_do_seletor(ruim, "h1") == 2.5, fonte_do_seletor(ruim, "h1")
    assert largura_em_ch(ruim, "h1") == 18
    assert grades_no_desktop(ruim) == 0, "nao ha grade de desktop nesse CSS"

    # o bloco @media se conta por chaves: regex ate a primeira '}' ou ate
    # '\n}' erra dos dois jeitos conforme a formatacao do CSS
    numa_linha = "@media (min-width:900px){.g{grid-template-columns:1fr 1fr}}"
    assert grades_no_desktop(numa_linha) == 1, "media query numa linha so"
    varias = ("@media (min-width:900px) {\n  .g {\n"
              "    grid-template-columns: repeat(3, 1fr);\n  }\n}\n")
    assert grades_no_desktop(varias) == 1, "media query indentada"
    # uma coluna so nao conta: continua sendo layout de celular
    assert grades_no_desktop("@media s{.g{grid-template-columns:1fr}}") == 0
    # fora de media query nao conta: o mobile pode ter grade de 1 coluna
    assert grades_no_desktop(".g{grid-template-columns:1fr 1fr}") == 0

    m = {**medir_de_texto(ruim), "footer": False, "regras": 14}
    f = avaliar(m)
    texto = " | ".join(f)
    assert any("2.5rem" in x for x in f), "h1 pequeno tem que falhar"
    assert any("18ch" in x for x in f), "o estrangulamento do titulo tem que falhar"
    assert any("hover" in x for x in f), "2 hovers tem que falhar"
    assert any("grade" in x for x in f), "desktop sem grade tem que falhar"
    assert any("footer" in x for x in f), "sem footer tem que falhar"
    assert any("tamanhos" in x or "distancia" in x for x in f), texto

    # ── um CSS que passa ────────────────────────────────────────────────────
    bom = """
    body { font-size: 1.0625rem; }
    h1 { font-size: 3.5rem; max-width: 32ch; }
    h2 { font-size: 2.25rem; } h3 { font-size: 1.375rem; }
    .peq { font-size: 0.875rem; }
    a:hover{}.b:hover{}.c:hover{}.d:hover{} :focus-visible{}
    .a{transition:a} .b{transition:b} .c{transition:c}
    @media (min-width: 760px) { .g { grid-template-columns: repeat(3, 1fr); } }
    """
    mb = {**medir_de_texto(bom), "footer": True, "regras": 20}
    assert avaliar(mb) == [], avaliar(mb)

    # razao: o que separa hierarquia de "tudo quase igual"
    quase = {**medir_de_texto("body{font-size:1rem} h1{font-size:2rem}"),
             "footer": True, "regras": 9, "hover": 9, "focus": 1,
             "transicao": 9, "grades_desktop": 1, "media_queries": 1}
    assert any("hierarquia" in x for x in avaliar(quase)), avaliar(quase)
    print("✅ autoteste passou")


def medir_de_texto(css: str) -> dict:
    """medir(), mas a partir de CSS em memoria. So o autoteste usa."""
    tamanhos = tamanhos_de_fonte(css)
    h1 = fonte_do_seletor(css, "h1")
    corpo = fonte_do_seletor(css, "body") or 1.0
    return {
        "h1_rem": h1, "corpo_rem": corpo,
        "razao": round(h1 / corpo, 2) if h1 and corpo else None,
        "tamanhos": tamanhos,
        "colados": sum(1 for a, b in zip(tamanhos, tamanhos[1:])
                       if b / a < DEGRAU_MINIMO),
        "h1_ch": largura_em_ch(css, "h1"),
        "hover": len(re.findall(r":hover", css)),
        "focus": len(re.findall(r":focus", css)),
        "transicao": len(re.findall(r"transition", css)),
        "grades_desktop": grades_no_desktop(css),
        "media_queries": len(re.findall(r"@media", css)),
        "footer": True, "regras": css.count("{"),
    }


def main():
    p = argparse.ArgumentParser(description="Mede o artesanato do site.")
    p.add_argument("dist", nargs="?", default="dist")
    p.add_argument("--autoteste", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.autoteste:
        autoteste()
        return 0
    return relatar(Path(a.dist))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Erro as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
