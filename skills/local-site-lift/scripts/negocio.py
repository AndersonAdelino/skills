#!/usr/bin/env python3
"""
negocio.py - consulta o perfil do negocio no Google Maps, via Apify.

  consultar "<nome> <cidade>" --out dados.json [--avaliacoes 8] [--fotos 8]
  fotos dados.json --out dist/img/real [--n 4]
  --autoteste

Serve para tres coisas que nenhuma outra fonte deu no primeiro site real:

  1. **Foto de verdade do lugar.** Instagram e Facebook bloqueiam requisicao sem
     login, e o site do proprio cliente costuma usar banco de imagem. O perfil
     do Google e a unica fonte acessivel de foto real.
  2. **Nota e numero de avaliacoes verificados.** Sem isso nao da para pos
     aggregateRating no schema, e nota inventada esta fora de questao.
  3. **Confrontar o que o site diz.** O perfil do Google e mantido pelo dono; o
     site costuma estar desatualizado. No primeiro teste o site dizia "Rua
     Manoel Felipe, 23" e o Google dizia "231", e o site anunciava sabado das
     7h30 as 12h com o Google marcando FECHADO.

Quem decide o que fazer com a divergencia e o agente, junto com o dono. Este
script so consulta.

APIFY_TOKEN e opcional: sem ele a skill funciona como antes, so sem esta etapa.
Custa por execucao, na casa de centavos de dolar por negocio.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ATOR = "compass~crawler-google-places"
APIFY = f"https://api.apify.com/v2/acts/{ATOR}/run-sync-get-dataset-items"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]


class Erro(RuntimeError):
    """Problema previsto, vira mensagem em vez de traceback."""


def _chave_no_env(env: Path, nome: str):
    """Le SOMENTE a chave pedida, como utf-8-sig (Bloco de Notas grava BOM)."""
    for linha in env.read_text(encoding="utf-8-sig").splitlines():
        if linha.lstrip().startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        if k.strip() == nome:
            v = v.strip().strip('"').strip("'")
            if v:
                return v
    return None


def carregar_chave(nome="APIFY_TOKEN") -> str:
    if os.environ.get(nome):
        return os.environ[nome]
    for partida in (Path.cwd(), Path(__file__).resolve().parent):
        for pasta in [partida, *partida.parents][:6]:
            env = pasta / ".env"
            if env.exists():
                achou = _chave_no_env(env, nome)
                if achou:
                    return achou
    raise Erro(
        f"falta {nome}. Esta etapa e opcional: sem ela o site sai igual, so "
        "sem foto real do lugar e sem nota verificada.\nPegue em "
        "https://console.apify.com/settings/integrations e grave num .env."
    )


# ── consulta ──────────────────────────────────────────────────────────────────

def consultar(busca: str, avaliacoes=8, fotos=8, timeout=300) -> dict:
    tok = carregar_chave()
    entrada = {
        "searchStringsArray": [busca],
        "maxCrawledPlacesPerSearch": 1,     # um negocio: e o que se paga
        "language": "pt-BR",
        "maxReviews": max(0, avaliacoes),
        "maxImages": max(0, fotos),
        "scrapeReviewsPersonalData": True,  # nome e data, para creditar
    }
    req = urllib.request.Request(
        f"{APIFY}?timeout={timeout}", data=json.dumps(entrada).encode(),
        headers={"Authorization": f"Bearer {tok}", "User-Agent": UA,
                 "Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    print(f"consultando o Google Maps: {busca} ...", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=timeout + 60) as r:
            itens = json.loads(r.read())
    except urllib.error.HTTPError as e:
        corpo = e.read()[:200].decode("utf-8", "replace")
        if e.code in (401, 403):
            raise Erro(f"o Apify recusou o token (HTTP {e.code}).") from None
        raise Erro(f"HTTP {e.code} no Apify: {corpo}") from None
    except urllib.error.URLError as e:
        raise Erro(f"nao consegui falar com o Apify: "
                   f"{getattr(e, 'reason', e)}") from None
    if not itens:
        raise Erro(f"o Google Maps nao achou '{busca}'. Tente com o nome exato "
                   "da placa e a cidade, ou confirme que o negocio tem perfil.")
    print(f"  achou em {time.time() - t0:.0f}s")
    return itens[0]


# ── leitura ───────────────────────────────────────────────────────────────────

def horario_por_dia(lugar: dict) -> dict:
    """{'segunda-feira': '07:30 to 17:30', 'sábado': 'Fechado', ...}

    A ordem que o Apify devolve comeca no dia de hoje, nao na segunda: ordenar
    importa para a comparacao nao parecer divergencia quando nao e.
    """
    bruto = {h.get("day"): h.get("hours") for h in (lugar.get("openingHours") or [])
             if isinstance(h, dict) and h.get("day")}
    ordenado = {d: bruto[d] for d in DIAS if d in bruto}
    for d, v in bruto.items():          # dia com nome fora do esperado nao some
        ordenado.setdefault(d, v)
    return ordenado


def fechado_em(lugar: dict) -> list:
    return [d for d, h in horario_por_dia(lugar).items()
            if h and "fechado" in str(h).lower()]


def resumo(lugar: dict) -> dict:
    """So o que interessa para o site, com nome previsivel."""
    return {
        "nome": lugar.get("title"),
        "categoria": lugar.get("categoryName"),
        "endereco": lugar.get("address"),
        "rua": lugar.get("street"),
        "bairro": (lugar.get("neighborhood") or ""),
        "cidade": lugar.get("city"),
        "uf": lugar.get("state"),
        "cep": lugar.get("postalCode"),
        "telefone": lugar.get("phone"),
        "site": lugar.get("website"),
        "nota": lugar.get("totalScore"),
        "avaliacoes": lugar.get("reviewsCount"),
        "distribuicao": lugar.get("reviewsDistribution") or {},
        "horario": horario_por_dia(lugar),
        "fechado_em": fechado_em(lugar),
        "fechado_definitivo": bool(lugar.get("permanentlyClosed")),
        "fechado_temporario": bool(lugar.get("temporarilyClosed")),
        "fotos": list(lugar.get("imageUrls") or []),
        "acessibilidade": (lugar.get("additionalInfo") or {}).get("Acessibilidade", []),
        "place_id": lugar.get("placeId"),
        "url_maps": lugar.get("url"),
        "comentarios": [
            {"nota": r.get("stars"), "quem": r.get("name"),
             "quando": (r.get("publishedAtDate") or "")[:10],
             "texto": (r.get("text") or "").strip()}
            for r in (lugar.get("reviews") or []) if r.get("text")
        ],
    }


def imprimir(d: dict):
    print(f"\n{d['nome']}  ({d.get('categoria') or 'sem categoria'})")
    print(f"  {d.get('endereco')}")
    print(f"  {d.get('telefone')}   {d.get('site') or ''}")
    if d["fechado_definitivo"]:
        print("  ATENCAO: marcado como FECHADO DEFINITIVAMENTE no Google")
    if d["fechado_temporario"]:
        print("  ATENCAO: marcado como fechado temporariamente")

    nota, n = d.get("nota"), d.get("avaliacoes")
    if nota:
        dist = d.get("distribuicao") or {}
        um = dist.get("oneStar", 0)
        print(f"\n  nota {nota} em {n} avaliacoes", end="")
        if n and um:
            print(f"   ({um} de 1 estrela, {um * 100 // n}%)", end="")
        print()
        if nota < 4.0:
            print("  Nota abaixo de 4.0: NAO use como selo no site. Leia os "
                  "comentarios de 1 estrela e conte ao dono.")

    print("\n  horario no Google:")
    for dia, h in d["horario"].items():
        print(f"    {dia:<14} {h}")
    if d["fechado_em"]:
        print(f"  fechado: {', '.join(d['fechado_em'])}")

    if d["acessibilidade"]:
        print(f"\n  acessibilidade: {json.dumps(d['acessibilidade'], ensure_ascii=False)[:120]}")

    if d["comentarios"]:
        print(f"\n  {len(d['comentarios'])} comentarios com texto:")
        for c in d["comentarios"][:6]:
            print(f"    {c['nota']}* {str(c['quem'])[:16]:<18} {c['quando']}  "
                  f"{c['texto'][:60]}")

    print(f"\n  {len(d['fotos'])} fotos disponiveis")
    print("\nCONFRONTE com o PRODUCT.md: endereco, horario e telefone do Google "
          "sao mantidos pelo dono e costumam estar mais certos que o site.")


# ── fotos ─────────────────────────────────────────────────────────────────────

def maior_resolucao(url: str) -> str:
    """Troca o sufixo de tamanho do CDN do Google por `=s0`, o original.

    As URLs vem como `.../AHRPTW...=w1920-h1080-k-no`, e a mesma URL sem
    sufixo nenhum devolve 512x288. Pedir `=s0` garante o maior que existe, que
    no caso testado era 1440x809. Nao ha versao maior: e o que a pessoa subiu.
    """
    if "googleusercontent.com" not in url:
        return url
    return url.split("=")[0] + "=s0"


def tipo_imagem(b: bytes):
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:2] == b"\xff\xd8":
        return "jpg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    return None


def baixar_fotos(dados: dict, destino: Path, n=4):
    """Baixa as fotos do perfil para o agente OLHAR e escolher.

    Elas sao mistura de foto do dono e foto de cliente, e o perfil nao
    distingue com confianca. Entram como candidatas, nunca direto no site: a
    do dono e legitima, a do cliente e outra conversa de permissao.
    """
    urls = (dados.get("fotos") or [])[:max(1, n)]
    if not urls:
        raise Erro("esse perfil nao trouxe foto nenhuma.")
    destino.mkdir(parents=True, exist_ok=True)
    salvas = []
    for i, u in enumerate(urls, 1):
        # `=s0` pede o ORIGINAL ao CDN do Google. A mesma URL sem sufixo
        # devolve 512x288, e foto de 512px exibida em banda larga num site
        # fica visivelmente borrada. Nao existe versao maior que o original,
        # entao este e o teto: use-o.
        u = maior_resolucao(u)
        try:
            b = urllib.request.urlopen(
                urllib.request.Request(u, headers={"User-Agent": UA}),
                timeout=60).read()
        except Exception as e:
            print(f"  {i}: falhou ({type(e).__name__})")
            continue
        t = tipo_imagem(b)
        if not t:
            print(f"  {i}: o que veio nao e imagem")
            continue
        p = destino / f"google-{i}.{t}"
        p.write_bytes(b)
        salvas.append(p)
        print(f"  {p}  ({len(b) // 1024} KB)")
    if not salvas:
        raise Erro("nenhuma foto pode ser baixada.")
    print(f"\n{len(salvas)} fotos em {destino}. OLHE antes de usar.")
    print("Foto do perfil e mistura de foto do dono e de cliente. Marque no "
          "PRODUCT.md como 'veio do Google Business, confirmar com o dono'.")
    return salvas


# ── autoteste ─────────────────────────────────────────────────────────────────

# Resposta reduzida da consulta real a Clinica Facil de Caico, 16/09/2026.
# Os numeros sao os que o Google devolveu, e foram o que expos tres erros no
# site que ja estava publicado.
REAL = {
    "title": "Clínica Fácil Caicó", "categoryName": "Clínica especializada",
    "address": "R. Manoel Felipe, 231 - Acampamento, Caicó - RN, 59300-000, Brasil",
    "street": "R. Manoel Felipe, 231", "city": "Caicó", "state": "Rio Grande do Norte",
    "postalCode": "59300-000", "phone": "+55 84 99690-9067",
    "website": "https://clinicafacilgrupo.com.br/",
    "totalScore": 3.9, "reviewsCount": 55,
    "reviewsDistribution": {"oneStar": 12, "twoStar": 2, "threeStar": 2,
                            "fourStar": 4, "fiveStar": 35},
    "permanentlyClosed": False, "temporarilyClosed": False,
    # o Apify devolve comecando no dia de hoje, nao na segunda
    "openingHours": [{"day": "quarta-feira", "hours": "07:30 to 17:30"},
                     {"day": "quinta-feira", "hours": "07:30 to 17:30"},
                     {"day": "sexta-feira", "hours": "07:30 to 17:30"},
                     {"day": "sábado", "hours": "Fechado"},
                     {"day": "domingo", "hours": "Fechado"},
                     {"day": "segunda-feira", "hours": "07:30 to 17:30"},
                     {"day": "terça-feira", "hours": "07:30 to 17:30"}],
    "imageUrls": ["https://lh3.googleusercontent.com/a", "https://x/b"],
    "reviews": [{"stars": 1, "name": "Fernanda Oliveira",
                 "publishedAtDate": "2026-05-26T10:00:00.000Z",
                 "text": "marcar atendimento pelo WhatsApp é impossível"},
                {"stars": 5, "name": "Andreia Fernandes",
                 "publishedAtDate": "2026-02-12T10:00:00.000Z",
                 "text": "Atendimento excelente"},
                {"stars": 4, "name": "Sem texto", "publishedAtDate": "2026-01-01",
                 "text": ""}],
}


def autoteste():
    d = resumo(REAL)

    # ── o horario vem comecando em HOJE, nao na segunda ─────────────────────
    # Sem ordenar, a comparacao com o site acusa divergencia que nao existe.
    assert list(d["horario"])[0] == "segunda-feira", list(d["horario"])
    assert list(d["horario"])[-1] == "domingo"
    assert len(d["horario"]) == 7

    # ── sabado fechado: o site publicado anunciava 7h30 as 12h ──────────────
    assert d["fechado_em"] == ["sábado", "domingo"], d["fechado_em"]

    # ── o endereco do Google tinha 231; o site dizia 23 ─────────────────────
    assert "231" in d["rua"], d["rua"]

    # ── nota abaixo de 4 nao vira selo ──────────────────────────────────────
    assert d["nota"] == 3.9 and d["avaliacoes"] == 55
    assert d["distribuicao"]["oneStar"] == 12, "22% de 1 estrela"

    # ── comentario sem texto nao entra ──────────────────────────────────────
    assert len(d["comentarios"]) == 2, d["comentarios"]
    assert all(c["texto"] for c in d["comentarios"])
    assert d["comentarios"][0]["quando"] == "2026-05-26", d["comentarios"][0]

    # ── negocio fechado tem que ser visivel ─────────────────────────────────
    assert resumo({**REAL, "permanentlyClosed": True})["fechado_definitivo"]

    # ── perfil vazio nao estoura ────────────────────────────────────────────
    v = resumo({})
    assert v["horario"] == {} and v["fotos"] == [] and v["comentarios"] == []
    assert v["fechado_em"] == []

    # ── bytes, nao extensao ─────────────────────────────────────────────────
    assert tipo_imagem(b"\xff\xd8\xff\xe0") == "jpg"
    assert tipo_imagem(b"<!doctype html>") is None

    # ── `=s0` ou a foto chega em 512x288 e borra numa banda larga ───────────
    g = "https://lh3.googleusercontent.com/gps-cs-s/ABC123"
    assert maior_resolucao(g + "=w1920-h1080-k-no") == g + "=s0"
    assert maior_resolucao(g) == g + "=s0", "URL sem sufixo tambem precisa"
    assert maior_resolucao(g + "=s0") == g + "=s0", "idempotente"
    # de outro dominio nao se mexe: o sufixo pode ser parte do caminho
    outro = "https://exemplo.com.br/foto=grande.jpg"
    assert maior_resolucao(outro) == outro

    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp(prefix="neg-teste-"))
    try:
        env = tmp / ".env"
        env.write_text("APIFY_TOKEN=apy123\nCPANEL_TOKEN=nao-e-minha\n",
                       encoding="utf-8-sig")
        assert env.read_bytes().startswith(b"\xef\xbb\xbf"), "o teste precisa do BOM"
        assert _chave_no_env(env, "APIFY_TOKEN") == "apy123"
        assert _chave_no_env(env, "PEXELS_API_KEY") is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("✅ autoteste passou")


# ── cli ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Consulta o perfil do negocio no Google Maps.")
    p.add_argument("comando", nargs="?", choices=["consultar", "fotos"])
    p.add_argument("alvo", nargs="?", help="busca, ou o dados.json")
    p.add_argument("--out")
    p.add_argument("--avaliacoes", type=int, default=8)
    p.add_argument("--fotos", type=int, default=8)
    p.add_argument("--n", type=int, default=4, help="quantas fotos baixar")
    p.add_argument("--autoteste", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()

    if a.autoteste:
        autoteste()
        return 0
    if not a.comando or not a.alvo:
        p.print_help()
        return 1

    if a.comando == "consultar":
        d = resumo(consultar(a.alvo, a.avaliacoes, a.fotos))
        imprimir(d)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(d, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            print(f"\ndados em {a.out}")
        return 0

    arq = Path(a.alvo)
    if not arq.exists():
        raise Erro(f"nao achei {arq}. Rode `consultar ... --out {arq}` antes.")
    baixar_fotos(json.loads(arq.read_text(encoding="utf-8")),
                 Path(a.out or "img/google"), a.n)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Erro as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
