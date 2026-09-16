#!/usr/bin/env python3
"""
validar-skills.py - as invariantes do repo, conferidas em vez de lembradas.

  python scripts/validar-skills.py

Existe por dois erros que passaram batido no mesmo dia:

  1. Um `:` dentro da `description` quebrou o YAML de duas skills, e elas
     PARARAM DE CARREGAR. Nada acusou: o carrossel some da lista, a
     local-site-lift passa a aparecer so com o titulo do H1. `/local-site-lift`
     nao executava a skill, e o agente saia cacando arquivo.
  2. Um merge sem conflito nenhum descartou a linha de CI de uma skill, a
     entrada dela no plugin.json e a linha de outra no README. Uma skill teria
     ficado fora do manifesto e fora do CI, instalada por ninguem.

Nenhum dos dois aparece lendo diff. Aparecem conferindo invariante.

So stdlib: sem PyYAML, o parser abaixo cobre o subconjunto que um frontmatter
de skill usa, e recusa o que o YAML de verdade recusaria.
"""

import json
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
CAMPOS_OBRIGATORIOS = ("name", "description")


def parse_frontmatter(texto: str):
    """(campos, erro). Erro = string dizendo o que o YAML recusaria."""
    if not texto.startswith("---"):
        return None, "nao comeca com ---"
    fim = texto.find("\n---", 3)
    if fim == -1:
        return None, "frontmatter sem fechamento ---"

    campos, chave, erro = {}, None, None
    for n, linha in enumerate(texto[3:fim].splitlines(), 2):
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        if linha.startswith("  ") or linha.startswith("\t"):
            if chave is None:
                return None, f"linha {n}: continuacao sem chave"
            campos[chave] = (campos[chave] + " " + linha.strip()).strip()
            continue
        m = re.match(r"^([A-Za-z][\w-]*):(.*)$", linha)
        if not m:
            return None, f"linha {n}: nao e 'chave: valor' -> {linha[:40]!r}"
        chave, valor = m.group(1), m.group(2).strip()
        if valor in (">", ">-", "|", "|-"):      # bloco: o resto vem indentado
            campos[chave] = ""
            continue
        if valor[:1] in ("'", '"') and valor[-1:] == valor[:1] and len(valor) > 1:
            campos[chave] = valor[1:-1]
            continue
        # Escalar solto. E aqui que o YAML de verdade recusa:
        if ": " in valor:
            erro = (f"linha {n}: '{chave}' tem ': ' dentro de um valor sem "
                    f"aspas — o YAML le como chave aninhada. Use 'chave: >-' "
                    f"e quebre o texto indentado abaixo.")
        elif valor[:1] in "[{":
            erro = (f"linha {n}: '{chave}' comeca com '{valor[:1]}' — o YAML le "
                    f"como lista/objeto. Ponha entre aspas duplas.")
        campos[chave] = valor
    return campos, erro


def validar():
    skills = sorted(p for p in (RAIZ / "skills").iterdir()
                    if (p / "SKILL.md").is_file())
    manifesto = json.loads((RAIZ / ".claude-plugin" / "plugin.json")
                           .read_text(encoding="utf-8"))
    ci = (RAIZ / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")

    falhas = []
    for s in skills:
        nome = s.name
        campos, erro = parse_frontmatter((s / "SKILL.md").read_text(encoding="utf-8"))

        if campos is None or erro:
            falhas.append(f"{nome}: frontmatter invalido — {erro}")
        else:
            for c in CAMPOS_OBRIGATORIOS:
                if not campos.get(c):
                    falhas.append(f"{nome}: falta '{c}' no frontmatter")
            if campos.get("name") != nome:
                falhas.append(f"{nome}: name='{campos.get('name')}' != pasta")
            if len(campos.get("description", "")) > 1024:
                falhas.append(f"{nome}: description com "
                              f"{len(campos['description'])} chars (limite 1024)")

        if f"./skills/{nome}" not in manifesto.get("skills", []):
            falhas.append(f"{nome}: fora do plugin.json — nao sera instalada")
        if f"skills/{nome}/)" not in readme:
            falhas.append(f"{nome}: sem linha na tabela do README")
        if not (s / "README.md").is_file():
            falhas.append(f"{nome}: sem README.md")

        for script in sorted((s / "scripts").glob("*.py")) if (s / "scripts").is_dir() else []:
            rel = f"skills/{nome}/scripts/{script.name}"
            if "--autoteste" not in script.read_text(encoding="utf-8"):
                falhas.append(f"{rel}: sem --autoteste")
            elif rel not in ci:
                falhas.append(f"{rel}: fora do CI — nunca sera testado")

    for declarada in manifesto.get("skills", []):
        if not (RAIZ / declarada.lstrip("./") / "SKILL.md").is_file():
            falhas.append(f"{declarada}: no plugin.json mas sem SKILL.md")

    print(f"{len(skills)} skills conferidas: " + ", ".join(s.name for s in skills))
    if falhas:
        print("\n".join("  ❌ " + f for f in falhas))
        return 1
    print("  ✅ frontmatter valido, manifesto, README e CI batendo")
    return 0


def autoteste():
    ok, e = parse_frontmatter("---\nname: x\ndescription: tudo bem aqui\n---\n")
    assert e is None and ok["name"] == "x", (ok, e)

    # o caso real: ': ' solto dentro da description derrubou duas skills
    _, e = parse_frontmatter("---\nname: x\ndescription: NAO publica: use outra\n---\n")
    assert e and "': '" in e, e

    # o outro caso real: argument-hint comecando com '['
    _, e = parse_frontmatter("---\nname: x\ndescription: ok\n"
                             "argument-hint: [--dry-run] [--forcar]\n---\n")
    assert e and "'['" in e, e

    # as duas formas corretas
    ok, e = parse_frontmatter('---\nname: x\ndescription: ok\n'
                              'argument-hint: "[--dry-run]"\n---\n')
    assert e is None and ok["argument-hint"] == "[--dry-run]", (ok, e)
    ok, e = parse_frontmatter("---\nname: x\ndescription: >-\n"
                              "  vale ter: dois pontos aqui\n  e mais linha\n---\n")
    assert e is None, e
    assert ok["description"] == "vale ter: dois pontos aqui e mais linha", ok

    assert parse_frontmatter("sem frontmatter")[1]
    assert parse_frontmatter("---\nname: x\n")[1], "sem fechamento"
    print("✅ autoteste passou")


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        autoteste()
    else:
        sys.exit(validar())
