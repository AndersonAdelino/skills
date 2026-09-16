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

# ── os limites, calibrados contra seis sites institucionais reais ────────────
#
# A primeira versao destes numeros foi inventada, e os seis sites de referencia
# REPROVARAM em metade deles. O que ficou e o que sobreviveu a medicao.
#
#   site                 h1(css)  tamanhos  hover  transition  shadow  <footer>
#   interprocess          inline      48     105       336       97      sim
#   allserviceindustrial   2.5rem     28      16        29       10      nao
#   spaceclass            inline      10     130       100       42      nao
#   savassiagronegocio     2.5rem     30      29        87       24      nao
#   pontualtecnologia      2.5rem     18     114       139       41      nao
#   megalihub              1.25rem    22      71        88       74      sim
#
# O que a tabela ensinou, e que derrubou checagens que eu tinha escrito:
#
#   - CONTAR TAMANHOS DE FONTE NO CSS NAO MEDE NADA. Todos tem de 10 a 48,
#     porque o CSS traz tema, framework e plugin inteiros. A checagem reprovava
#     6 de 6 sites bons. Removida.
#   - O h1 DECLARADO no CSS tambem nao vale: metade destes sites define o
#     tamanho real inline, pelo construtor de pagina. So o valor renderizado
#     diz algo, e isso exige browser.
#   - `<footer>` nao vale: 4 de 6 usam `<div class="footer">`. Removida.
#
# O que sobreviveu foi a DENSIDADE DE INTERACAO, e por uma margem enorme: o
# site ruim tinha 2 hover e 1 transition; o mais discreto dos bons tem 16 e 29.
# Nao e questao de gosto, e de ordem de grandeza.
HOVER_MINIMO = 12           # o mais discreto dos seis tem 16
TRANSICAO_MINIMA = 20       # o mais discreto tem 29
SOMBRA_MINIMA = 8           # o mais discreto tem 10

# Estes dois continuam valendo porque sao defeito, nao estilo, e nenhum dos
# seis comete: h1 estrangulado em coluna de leitura, e desktop sem grade.
CH_MINIMO_TITULO = 24       # h1 { max-width: 18ch } foi o defeito da Stella
RAZAO_MINIMA = 2.0          # so avisa quando da para medir os dois no CSS


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
    return {
        "h1_rem": h1,
        "corpo_rem": corpo,
        "razao": round(h1 / corpo, 2) if h1 and corpo else None,
        "tamanhos": tamanhos,
        "sombra": len(re.findall(r"box-shadow", css)),
        "h1_ch": largura_em_ch(css, "h1"),
        "hover": len(re.findall(r":hover", css)),
        "focus": len(re.findall(r":focus", css)),
        "transicao": len(re.findall(r"transition", css)),
        "grades_desktop": grades_no_desktop(css),
        "media_queries": len(re.findall(r"@media", css)),
        "regras": css.count("{"),
    }


def avaliar(m: dict) -> list:
    """Lista de falhas. Cada uma diz o numero medido e a referencia real."""
    f = []
    if m["h1_ch"] and m["h1_ch"] < CH_MINIMO_TITULO:
        f.append(f"h1 com max-width de {int(m['h1_ch'])}ch: o titulo quebra em "
                 "linhas curtas e deixa a tela vazia ao lado. `ch` e para "
                 "paragrafo, nunca para titulo")
    if m["razao"] and m["razao"] < RAZAO_MINIMA:
        f.append(f"h1 tem {m['razao']}x o corpo do texto. Sem contraste de "
                 "tamanho nao existe hierarquia, so tamanhos parecidos")
    if m["hover"] < HOVER_MINIMO:
        f.append(f"{m['hover']} estado(s) :hover em {m['regras']} regras. O "
                 f"mais discreto dos seis sites de referencia tem 16, e o site "
                 "que foi reprovado tinha 2: nada respondia ao cursor")
    if m["transicao"] < TRANSICAO_MINIMA:
        f.append(f"{m['transicao']} transicao(oes). A referencia mais discreta "
                 "tem 29, e o site reprovado tinha 1. Troca seca de estado e o "
                 "que mais denuncia site amador")
    if m["sombra"] < SOMBRA_MINIMA:
        f.append(f"{m['sombra']} box-shadow. A referencia mais discreta tem 10: "
                 "sem profundidade nenhuma tudo fica no mesmo plano")
    if not m["focus"]:
        f.append("nenhum estado de foco: quem navega por teclado fica perdido")
    if m["media_queries"] and not m["grades_desktop"]:
        f.append("nenhuma grade de varias colunas no desktop. O layout largo "
                 "vira a coluna do celular esticada, com metade da tela vazia")
    return f


def relatar(dist: Path) -> int:
    m = medir(dist)
    print(f"\n{dist}")
    print(f"  h1 {m['h1_rem']}rem  corpo {m['corpo_rem']}rem  razao {m['razao']}x")
    print(f"  hover {m['hover']}  focus {m['focus']}  transicao "
          f"{m['transicao']}  sombra {m['sombra']}   ({m['regras']} regras)")
    print(f"  {m['grades_desktop']} grade(s) de varias colunas no desktop")
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

    f = avaliar({**medir_de_texto(ruim), "regras": 14})
    assert any("18ch" in x for x in f), "titulo estrangulado tem que falhar"
    assert any("hover" in x for x in f), "2 hovers tem que falhar"
    assert any("transicao" in x for x in f), "1 transicao tem que falhar"
    assert any("grade" in x for x in f), "desktop sem grade tem que falhar"

    # ── e o que NAO pode mais falhar, porque reprovava 6 de 6 referencias ───
    # Contar tamanho de fonte no CSS mede o framework, nao o design.
    muitos = "body{font-size:1rem}" + "".join(
        f".c{i}{{font-size:{0.8 + i*0.03:.2f}rem}}" for i in range(20))
    muitos += ("h1{font-size:3rem}" + "a:hover{}" * 14 + ":focus{}"
               + ".t{transition:a}" * 22 + ".s{box-shadow:a}" * 10
               + "@media s{.g{grid-template-columns:1fr 1fr}}")
    assert avaliar({**medir_de_texto(muitos), "regras": 60}) == [], \
        "contar tamanhos de fonte reprovava todos os seis sites bons"

    # ── um CSS que passa, com a densidade das referencias ───────────────────
    bom = ("body{font-size:1.0625rem} h1{font-size:3.5rem;max-width:32ch}"
           + "a:hover{}" * 14 + ":focus-visible{}" + ".t{transition:a}" * 22
           + ".s{box-shadow:0 1px 2px}" * 10
           + "@media (min-width:760px){.g{grid-template-columns:repeat(3,1fr)}}")
    assert avaliar({**medir_de_texto(bom), "regras": 60}) == [], \
        avaliar({**medir_de_texto(bom), "regras": 60})

    # razao: o que separa hierarquia de "tudo quase igual"
    quase = {**medir_de_texto("body{font-size:1rem} h1{font-size:1.5rem}"),
             "regras": 9, "hover": 20, "focus": 1, "transicao": 30,
             "sombra": 10, "grades_desktop": 1, "media_queries": 1}
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
        "sombra": len(re.findall(r"box-shadow", css)),
        "h1_ch": largura_em_ch(css, "h1"),
        "hover": len(re.findall(r":hover", css)),
        "focus": len(re.findall(r":focus", css)),
        "transicao": len(re.findall(r"transition", css)),
        "grades_desktop": grades_no_desktop(css),
        "media_queries": len(re.findall(r"@media", css)),
        "sombra": len(re.findall(r"box-shadow", css)),
        "regras": css.count("{"),
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
