#!/usr/bin/env python3
"""
deploy-cpanel.py - publica uma pasta estatica no cPanel (HostGator) via UAPI.

  deploy-cpanel.py [--env .env] [--dry-run] [--inseguro]
  deploy-cpanel.py --autoteste

Le CPANEL_HOST, CPANEL_USER, CPANEL_TOKEN, CPANEL_PORT, DEPLOY_PATH,
SOURCE_DIR e SITE_URL do .env. Nao imprime o token em lugar nenhum.

So biblioteca padrao: a skill roda na maquina de quem contratou o site, e
`pip install` na hora do deploy e um jeito de o deploy falhar.

Substitui o deploy-cpanel.sh, que tinha tres defeitos que este arquivo existe
para nao repetir:

  1. Decidia sucesso com `grep '"status":1'` na resposta inteira. Como o UAPI
     devolve status por arquivo DENTRO de `data`, uma resposta de erro com
     {"errors":["token invalido"],"status":0,"data":[{"status":1}]} passava como
     sucesso: o deploy imprimia "ok" para todo arquivo e nao subia nada.
     Aqui o JSON e lido de verdade, o status do topo e do arquivo separados.
  2. Passava o token como argumento do curl, entao ele aparecia em `ps aux`
     durante todo o upload - enquanto o comentario do script dizia
     "Nao imprime o token". Aqui nao ha subprocesso: o header vai no urllib.
  3. Documentava que um index.php velho continua ganhando da home nova, ja
     tinha a listagem da pasta remota na mao, e nao olhava para ela. Aqui a
     listagem e conferida antes, e o site publicado e conferido depois.
"""

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CHAVES = ("CPANEL_HOST", "CPANEL_USER", "CPANEL_TOKEN", "CPANEL_PORT",
          "DEPLOY_PATH", "SOURCE_DIR", "SITE_URL")
PADRAO = {"CPANEL_PORT": "2083", "DEPLOY_PATH": "public_html",
          "SOURCE_DIR": "dist"}

IGNORAR = {".DS_Store", "Thumbs.db", ".env", ".gitignore", ".git"}
INDICES_QUE_GANHAM = ("index.php", "index.htm", "default.php", "default.htm")

# design-floor.md manda "imagens com tamanho realista (nao 4k no hero)". Aviso,
# nao bloqueio: pode haver motivo. 500 KB ja e muito para 4G no sol.
LIMITE_IMAGEM = 500 * 1024
EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


class Erro(RuntimeError):
    """Problema previsto, mostrado como mensagem em vez de traceback."""


# ── .env ──────────────────────────────────────────────────────────────────────

def _chaves_no_env(env: Path, nomes) -> dict:
    """Le SOMENTE as chaves pedidas. Nao faz `source`, nao exporta nada.

    O .sh fazia `set -a; source .env`, o que executa o arquivo como shell e
    joga TODAS as variaveis dele no ambiente de todo subprocesso. No projeto de
    um cliente esse .env costuma ter credencial que nao tem nada a ver com
    deploy de site.

    Le como utf-8-sig: no Windows, Bloco de Notas e `Out-File -Encoding utf8`
    gravam BOM, e com utf-8 puro a primeira chave do arquivo vira
    "﻿CPANEL_HOST" e nunca casa com o nome.
    """
    achadas = {}
    for linha in env.read_text(encoding="utf-8-sig").splitlines():
        if linha.lstrip().startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        k = k.strip()
        if k in nomes:
            v = v.strip().strip('"').strip("'")
            if v:
                achadas[k] = v
    return achadas


def _rastreado_pelo_git(caminho: Path) -> bool:
    """True se o arquivo esta no indice do git. Token no git e irreversivel:
    quem clonou ja tem, e reescrever a historia nao tira de la."""
    try:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", str(caminho)],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False        # sem git instalado ou fora de repo: nada a conferir


def carregar_config(env_file: Path) -> dict:
    if not env_file.exists():
        raise Erro(
            f"nao achei {env_file}. Copie assets/env.example para .env e "
            "preencha host, usuario e token do cPanel."
        )
    if _rastreado_pelo_git(env_file):
        raise Erro(
            f"{env_file} esta rastreado pelo git. Rode:\n\n"
            f"  git rm --cached {env_file}\n\n"
            "confira que .env esta no .gitignore, e rode o deploy de novo."
        )

    cfg = dict(PADRAO)
    cfg.update(_chaves_no_env(env_file, CHAVES))
    for obrigatoria in ("CPANEL_HOST", "CPANEL_USER", "CPANEL_TOKEN"):
        if not cfg.get(obrigatoria):
            raise Erro(f"{obrigatoria} esta vazio no {env_file}.")
    cfg["DEPLOY_PATH"] = cfg["DEPLOY_PATH"].strip("/")
    return cfg


# ── UAPI ──────────────────────────────────────────────────────────────────────

def status_do_topo(resposta: dict) -> bool:
    """Le o status do TOPO da resposta, e so ele.

    O .sh dava grep de '"status":1' na resposta inteira. Como `upload_files`
    devolve um status por arquivo dentro de `data`, resposta de erro com
    sucesso aninhado passava batido - o caso que este projeto quer nunca mais
    ver.
    """
    if not isinstance(resposta, dict):
        return False
    return str(resposta.get("status", "")) == "1"


def erros_de(resposta) -> str:
    if not isinstance(resposta, dict):
        return "resposta do cPanel nao era JSON"
    erros = resposta.get("errors") or resposta.get("messages") or []
    if isinstance(erros, str):
        erros = [erros]
    return "; ".join(str(e) for e in erros) or "sem detalhe do cPanel"


def upload_aceito(resposta) -> bool:
    """A decisao inteira num lugar so: o topo aceitou E nenhum arquivo foi
    recusado. Era aqui que o .sh errava, entao aqui tem teste."""
    return status_do_topo(resposta) and not uploads_com_falha(resposta)


def uploads_com_falha(resposta: dict) -> list:
    """Arquivos que o cPanel recusou, mesmo com o status do topo em 1.

    O status aninhado existe e importa - o defeito do .sh nao era olhar para
    ele, era confundir com o status do topo.
    """
    dados = resposta.get("data") or {}
    itens = dados.get("uploads") if isinstance(dados, dict) else None
    if not isinstance(itens, list):
        return []
    return [i for i in itens
            if isinstance(i, dict) and str(i.get("status", "1")) != "1"]


class Cpanel:
    def __init__(self, cfg: dict, inseguro=False):
        self.base = (f"https://{cfg['CPANEL_HOST']}:{cfg['CPANEL_PORT']}"
                     "/execute")
        # O token vai no header do request, nunca em argv. O .sh montava
        # `curl -H "Authorization: cpanel user:TOKEN"`, e argumento de processo
        # e publico: qualquer `ps aux` na maquina lia o token inteiro.
        self._auth = f"cpanel {cfg['CPANEL_USER']}:{cfg['CPANEL_TOKEN']}"
        if inseguro:
            self.ctx = ssl._create_unverified_context()
        else:
            self.ctx = ssl.create_default_context()

    def _abrir(self, req: urllib.request.Request):
        req.add_header("Authorization", self._auth)
        try:
            with urllib.request.urlopen(req, timeout=120,
                                        context=self.ctx) as r:
                bruto = r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise Erro(
                    "o cPanel recusou o token (HTTP "
                    f"{e.code}). Confira usuario, token, e se o token tem "
                    "permissao de File Manager."
                ) from None
            raise Erro(f"HTTP {e.code} do cPanel") from None
        except urllib.error.URLError as e:
            motivo = getattr(e, "reason", e)
            if isinstance(motivo, ssl.SSLError):
                raise Erro(
                    f"o certificado de {self.base} nao passou na verificacao "
                    f"({motivo}). Em hospedagem compartilhada o cPanel as vezes "
                    "responde com o certificado do servidor, nao do dominio. "
                    "Se for o caso, rode com --inseguro ciente de que o token "
                    "viaja nessa conexao."
                ) from None
            raise Erro(f"nao consegui falar com o cPanel: {motivo}") from None
        try:
            return json.loads(bruto)
        except json.JSONDecodeError:
            raise Erro(
                "o cPanel respondeu algo que nao e JSON. Normalmente e a "
                "pagina de login: confira a porta (2083) e o host."
            ) from None

    def chamar(self, modulo: str, funcao: str, **params):
        qs = urllib.parse.urlencode(params)      # encode de verdade: caminho
        url = f"{self.base}/{modulo}/{funcao}"   # com espaco quebrava o .sh
        if qs:
            url += "?" + qs
        return self._abrir(urllib.request.Request(url))

    def listar(self, pasta: str) -> dict:
        return self.chamar("Fileman", "list_files", dir=pasta)

    def criar_pasta(self, pai: str, nome: str) -> dict:
        return self.chamar("Fileman", "mkdir", path=pai, name=nome)

    def enviar(self, pasta_remota: str, arquivo: Path, nome: str) -> dict:
        corpo, tipo = corpo_multipart(
            {"dir": pasta_remota}, "file-1", nome, arquivo.read_bytes())
        req = urllib.request.Request(
            f"{self.base}/Fileman/upload_files", data=corpo, method="POST")
        req.add_header("Content-Type", tipo)
        return self._abrir(req)


def corpo_multipart(campos: dict, campo_arquivo: str, nome: str,
                    conteudo: bytes):
    """multipart/form-data na mao - a stdlib nao traz e nao vale uma dependencia."""
    fronteira = "----deploy" + os.urandom(16).hex()
    seguro = nome.replace('"', "").replace("\r", "").replace("\n", "")
    partes = []
    for k, v in campos.items():
        partes.append(
            f'--{fronteira}\r\nContent-Disposition: form-data; name="{k}"'
            f"\r\n\r\n{v}\r\n".encode())
    partes.append(
        f'--{fronteira}\r\nContent-Disposition: form-data; '
        f'name="{campo_arquivo}"; filename="{seguro}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode())
    partes.append(conteudo)
    partes.append(f"\r\n--{fronteira}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


# ── o que sobe ────────────────────────────────────────────────────────────────

def arquivos_para_enviar(origem: Path):
    """(caminho local, caminho relativo POSIX), em ordem, sem lixo."""
    saida = []
    for p in sorted(origem.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(origem)
        if any(parte in IGNORAR for parte in rel.parts):
            continue
        if rel.name.startswith(".env"):
            continue
        saida.append((p, rel.as_posix()))
    return saida


def pastas_para_criar(relativos, deploy_path: str):
    """Pastas remotas, pai antes de filho."""
    pastas = set()
    for rel in relativos:
        partes = rel.split("/")[:-1]
        for i in range(1, len(partes) + 1):
            pastas.add("/".join(partes[:i]))
    return [f"{deploy_path}/{p}" for p in sorted(pastas, key=lambda x: (x.count("/"), x))]


def imagens_pesadas(arquivos):
    return [(rel, p.stat().st_size) for p, rel in arquivos
            if p.suffix.lower() in EXT_IMAGEM and p.stat().st_size > LIMITE_IMAGEM]


def indices_conflitantes(resposta_listagem: dict) -> list:
    """index.php velho continua ganhando de index.html novo. O .sh documentava
    isso, ja tinha a listagem na mao, e nao conferia."""
    dados = resposta_listagem.get("data") or []
    if not isinstance(dados, list):
        return []
    nomes = {i.get("file") for i in dados if isinstance(i, dict)}
    return [n for n in INDICES_QUE_GANHAM if n in nomes]


def titulo_de(html: str):
    """<title> do index, usado como marca para conferir o site publicado."""
    baixo = html.lower()
    i = baixo.find("<title")
    if i == -1:
        return None
    i = baixo.find(">", i)
    f = baixo.find("</title>", i)
    if i == -1 or f == -1:
        return None
    return html[i + 1:f].strip() or None


def conferir_publicado(url: str, marca, inseguro=False):
    """Busca o site no ar. Devolve (ok, recado). Este e o unico teste que
    responde a pergunta que interessa: abriu, e e a home nova?"""
    ctx = (ssl._create_unverified_context() if inseguro
           else ssl.create_default_context())
    req = urllib.request.Request(url, headers={"User-Agent": "deploy-cpanel"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            corpo = r.read(200_000).decode("utf-8", "replace")
            codigo = r.status
    except urllib.error.HTTPError as e:
        return False, f"{url} respondeu HTTP {e.code}"
    except urllib.error.URLError as e:
        motivo = getattr(e, "reason", e)
        if isinstance(motivo, ssl.SSLError):
            return False, (f"{url} ainda sem SSL valido ({motivo}). Na "
                           "HostGator o certificado leva alguns minutos.")
        return False, f"nao consegui abrir {url}: {motivo}"
    if codigo != 200:
        return False, f"{url} respondeu HTTP {codigo}"
    if marca and marca not in corpo:
        return False, (
            f"{url} abriu, mas nao e a home que subiu (nao achei "
            f"“{marca}”). Costuma ser um index.php velho ganhando do "
            "index.html novo, ou cache do navegador/CDN."
        )
    return True, f"{url} no ar com a home nova"


# ── deploy ────────────────────────────────────────────────────────────────────

def deploy(cfg: dict, dry_run=False, inseguro=False) -> int:
    origem = Path(cfg["SOURCE_DIR"])
    if not origem.is_dir():
        raise Erro(f"a pasta {origem} nao existe - gere o site em dist/ antes.")
    arquivos = arquivos_para_enviar(origem)
    if not arquivos:
        raise Erro(f"{origem} esta vazia.")

    destino = cfg["DEPLOY_PATH"]
    print(f"Destino: {cfg['CPANEL_USER']}@{cfg['CPANEL_HOST']}:"
          f"{cfg['CPANEL_PORT']}/{destino}")
    print(f"Origem:  {origem}  ({len(arquivos)} arquivos)")

    for rel, tamanho in imagens_pesadas(arquivos):
        print(f"aviso: {rel} tem {tamanho // 1024} KB. Acima de "
              f"{LIMITE_IMAGEM // 1024} KB o site fica lento no 4G - comprima "
              "antes de subir.")

    if dry_run:
        print("Modo:    dry-run (nada sera enviado)\n")
        for pasta in pastas_para_criar([r for _, r in arquivos], destino):
            print(f"  mkdir  {pasta}")
        for _, rel in arquivos:
            print(f"  upload {rel}")
        print(f"\n{len(arquivos)} arquivos seriam enviados.")
        return 0

    cp = Cpanel(cfg, inseguro=inseguro)

    listagem = cp.listar(destino)
    if not status_do_topo(listagem):
        raise Erro(
            f"nao consegui listar {destino}: {erros_de(listagem)}\n"
            "Confira host, usuario, token, porta 2083, e se a pasta existe "
            "(addon domain costuma ter document root proprio)."
        )
    conflitos = indices_conflitantes(listagem)
    if conflitos:
        print(f"\naviso: {destino} ja tem {', '.join(conflitos)}. O Apache "
              "serve esse arquivo antes do index.html novo, entao a home velha "
              "continua no ar mesmo com o deploy dando certo. Apague pelo "
              "Gerenciador de Arquivos do cPanel.\n")

    for pasta in pastas_para_criar([r for _, r in arquivos], destino):
        pai, _, nome = pasta.rpartition("/")
        r = cp.criar_pasta(pai, nome)
        if not status_do_topo(r) and "exist" not in erros_de(r).lower():
            print(f"aviso: mkdir {pasta}: {erros_de(r)}")

    enviados, falhas = 0, []
    for caminho, rel in arquivos:
        pasta_remota = f"{destino}/{rel}".rsplit("/", 1)[0]
        r = cp.enviar(pasta_remota, caminho, Path(rel).name)
        if upload_aceito(r):
            print(f"  ok     {rel}")
            enviados += 1
        else:
            recusados = uploads_com_falha(r)
            detalhe = erros_de(r)
            if recusados:
                detalhe = "; ".join(str(i.get("reason") or i) for i in recusados)
            print(f"  FALHOU {rel}: {detalhe}", file=sys.stderr)
            falhas.append(rel)

    print(f"\nEnviados: {enviados}/{len(arquivos)}")
    if falhas:
        raise Erro(f"{len(falhas)} arquivo(s) nao subiram: {', '.join(falhas)}")

    # Sondar o que foi entregue, nao o que foi pedido.
    url = cfg.get("SITE_URL") or f"https://{cfg['CPANEL_HOST']}"
    index = origem / "index.html"
    marca = titulo_de(index.read_text(encoding="utf-8", errors="replace")) \
        if index.exists() else None
    ok, recado = conferir_publicado(url, marca, inseguro=inseguro)
    print(("\n✅ " if ok else "\n⚠️  ") + recado)
    if ok:
        print("Abra no celular e confira o botao do WhatsApp e o mapa.")
    return 0 if ok else 1


# ── autoteste ─────────────────────────────────────────────────────────────────

# Estas cinco respostas sao o bug do .sh. As tres do meio passavam como sucesso
# com o `grep '"status":1'`, e o deploy dizia "Pronto" sem ter subido nada.
RESPOSTAS = [
    ('{"status":1,"data":[]}', True),
    ('{"status":0,"errors":["Acesso negado"]}', False),
    ('{"status":10,"errors":["falhou"]}', False),
    ('{"status":0,"errors":["x"],"data":{"nlink":1,"status":1}}', False),
    ('{"errors":["token invalido"],"status":0,"data":[{"f":"a","status":1}]}',
     False),
]


def autoteste():
    import tempfile, shutil

    # ── o defeito que motivou reescrever ────────────────────────────────────
    for bruto, esperado in RESPOSTAS:
        assert status_do_topo(json.loads(bruto)) is esperado, bruto
    assert status_do_topo(None) is False
    assert status_do_topo({"status": "1"}) is True

    # status aninhado continua valendo - para o que ele realmente serve
    ok_fora_falha_dentro = {"status": 1, "data": {"uploads": [
        {"file": "a.jpg", "status": 0, "reason": "sem espaco"},
        {"file": "b.css", "status": 1}]}}
    assert len(uploads_com_falha(ok_fora_falha_dentro)) == 1
    assert uploads_com_falha({"status": 1, "data": {"uploads": []}}) == []
    assert uploads_com_falha({"status": 1, "data": []}) == []

    # a decisao de "subiu?" - nenhuma das duas metades pode passar sozinha
    assert upload_aceito({"status": 1, "data": {"uploads": [{"status": 1}]}})
    assert not upload_aceito(ok_fora_falha_dentro), "falha aninhada tem que barrar"
    for bruto, esperado in RESPOSTAS:
        assert upload_aceito(json.loads(bruto)) is esperado, bruto

    assert "token invalido" in erros_de(
        json.loads('{"errors":["token invalido"],"status":0}'))

    # ── index.php velho ganhando da home nova ───────────────────────────────
    listagem = {"status": 1, "data": [{"file": "index.php"},
                                      {"file": "imagem.png"}]}
    assert indices_conflitantes(listagem) == ["index.php"]
    assert indices_conflitantes({"status": 1, "data": [{"file": "a.html"}]}) == []
    assert indices_conflitantes({"status": 1, "data": None}) == []

    # ── marca da home publicada ─────────────────────────────────────────────
    assert titulo_de("<html><head><title>Padaria X em Centro</title>") == \
        "Padaria X em Centro"
    assert titulo_de('<TITLE >Oficina</TITLE>') == "Oficina"
    assert titulo_de("<html><head></head>") is None

    # ── multipart ───────────────────────────────────────────────────────────
    corpo, tipo = corpo_multipart({"dir": "public_html/img"}, "file-1",
                                  'a"b.jpg', b"\xff\xd8bytes")
    fronteira = tipo.split("boundary=")[1]
    assert corpo.startswith(f"--{fronteira}\r\n".encode())
    assert corpo.endswith(f"\r\n--{fronteira}--\r\n".encode())
    assert b'name="dir"\r\n\r\npublic_html/img\r\n' in corpo
    assert b'filename="ab.jpg"' in corpo, "aspas no nome quebram o header"
    assert b"\xff\xd8bytes" in corpo, "o conteudo binario tem que ir inteiro"

    tmp = Path(tempfile.mkdtemp(prefix="lsl-teste-"))
    try:
        # ── .env: BOM e a chave vizinha ─────────────────────────────────────
        env = tmp / ".env"
        env.write_text("CPANEL_HOST=meusite.com.br\nCPANEL_TOKEN=tok123\n"
                       "OPENAI_API_KEY=credencial-do-cliente\n",
                       encoding="utf-8-sig")
        assert env.read_bytes().startswith(b"\xef\xbb\xbf"), "o teste precisa do BOM"
        lidas = _chaves_no_env(env, CHAVES)
        assert lidas["CPANEL_HOST"] == "meusite.com.br", lidas
        assert lidas["CPANEL_TOKEN"] == "tok123"
        assert "OPENAI_API_KEY" not in lidas, "so as chaves pedidas"
        vazio = tmp / "vazio.env"
        vazio.write_text("CPANEL_TOKEN=\n# CPANEL_HOST=comentado\n",
                         encoding="utf-8")
        assert _chaves_no_env(vazio, CHAVES) == {}

        # ── o que sobe, e em que ordem ──────────────────────────────────────
        dist = tmp / "dist"
        (dist / "img").mkdir(parents=True)
        (dist / "css").mkdir()
        for rel, dados in [("index.html", b"<title>Casa</title>"),
                           ("css/estilo.css", b"body{}"),
                           ("img/foto.jpg", b"x" * (LIMITE_IMAGEM + 1)),
                           ("img/logo.png", b"y"),
                           (".DS_Store", b"lixo"),
                           (".env", b"CPANEL_TOKEN=segredo")]:
            (dist / rel).write_bytes(dados)
        arquivos = arquivos_para_enviar(dist)
        rels = [r for _, r in arquivos]
        assert ".DS_Store" not in rels and ".env" not in rels, rels
        assert set(rels) == {"index.html", "css/estilo.css", "img/foto.jpg",
                             "img/logo.png"}, rels

        pastas = pastas_para_criar(rels, "public_html")
        assert pastas == ["public_html/css", "public_html/img"], pastas
        fundo = pastas_para_criar(["a/b/c/d.txt"], "public_html")
        assert fundo == ["public_html/a", "public_html/a/b",
                         "public_html/a/b/c"], fundo   # pai antes de filho

        pesadas = imagens_pesadas(arquivos)
        assert [r for r, _ in pesadas] == ["img/foto.jpg"], pesadas

        # ── .env versionado trava o deploy ──────────────────────────────────
        assert _rastreado_pelo_git(tmp / "nao-existe.env") is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── query string com espaco: o que quebrava o .sh ───────────────────────
    assert urllib.parse.urlencode({"dir": "public_html/oficina x"}) == \
        "dir=public_html%2Foficina+x"

    print("✅ autoteste passou")


# ── cli ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Publica uma pasta estatica no cPanel da HostGator.")
    p.add_argument("--env", default=".env", help="arquivo .env (padrao: .env)")
    p.add_argument("--dry-run", action="store_true",
                   help="mostra o que subiria, sem enviar nada")
    p.add_argument("--inseguro", action="store_true",
                   help="nao verifica o certificado do cPanel. O TOKEN VIAJA "
                        "NESSA CONEXAO: use so quando o erro for de certificado "
                        "do servidor compartilhado, nunca em rede publica")
    p.add_argument("--autoteste", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.autoteste:
        autoteste()
        return 0
    if args.inseguro:
        print("aviso: verificacao de certificado desligada. O token viaja "
              "nessa conexao.\n", file=sys.stderr)
    cfg = carregar_config(Path(args.env))
    return deploy(cfg, dry_run=args.dry_run, inseguro=args.inseguro)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Erro as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
