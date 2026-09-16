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
import re
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

# O cPanel da HostGator fica atras do Cloudflare, que recusa requisicao sem
# User-Agent com 403 e "error code: 1010", antes mesmo de olhar o token.
UA_NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# Imagem pesada e o que mais atrasa site de comercio local no 4G. Aviso, nao
# bloqueio: pode haver motivo para uma foto grande.
LIMITE_IMAGEM = 500 * 1024
EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


class Erro(RuntimeError):
    """Problema previsto, mostrado como mensagem em vez de traceback."""


def limpar_host(valor: str) -> str:
    """So o hostname, venha o que vier.

    Todo mundo cola a URL que abre o painel, com https:// e barra no fim. Sem
    isto o script monta `https://https://dominio/:2083/execute` e falha com uma
    mensagem que nao ajuda ninguem.
    """
    v = (valor or "").strip()
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", v, flags=re.I)  # tira o esquema
    v = v.split("/", 1)[0]                                    # tira o caminho
    v = v.split("@")[-1]                                      # tira user:senha@
    if v.count(":") == 1:                                     # tira a porta
        v = v.split(":")[0]
    return v.strip(". ")


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


def _envs_ate_a_raiz(partida: Path, limite=4):
    # limite=4 cobre projeto/clientes/<nome>/ com folga e para antes de chegar
    # na home do usuario, onde um .env de outro projeto seria lido sem querer.
    """Todo .env de `partida` para cima, do mais DISTANTE para o mais proximo.

    Isso e o que faz uma conta de hospedagem servir varios clientes:

      projeto/.env                      CPANEL_HOST, CPANEL_USER, CPANEL_TOKEN
      projeto/clientes/padaria/.env     DEPLOY_PATH, SITE_URL
      projeto/clientes/oficina/.env     DEPLOY_PATH, SITE_URL

    A credencial fica num lugar so, e cada cliente diz apenas para onde vai.
    Aplicados nesta ordem, o mais proximo ganha: o cliente pode sobrescrever
    qualquer coisa, inclusive a conta, se um deles tiver hospedagem propria.
    """
    achados = []
    for pasta in [partida, *partida.parents][:limite]:
        env = pasta / ".env"
        if env.exists():
            achados.append(env)
    return list(reversed(achados))


def carregar_config(env_file=None, exigir_credenciais=True) -> dict:
    """Config na ordem: padrao -> .env das pastas acima -> .env local -> ambiente.

    `env_file` forca um arquivo unico e desliga a busca para cima.

    O ambiente ganha de tudo, para CI e automacao rodarem sem gravar
    credencial em disco.

    `exigir_credenciais=False` e o --dry-run: ele nao abre conexao nenhuma,
    entao pedir host e token so para listar o que subiria era barreira sem
    motivo.
    """
    cfg = dict(PADRAO)
    if env_file is not None:
        arquivos = [Path(env_file)] if Path(env_file).exists() else []
        if not arquivos and exigir_credenciais:
            raise Erro(f"nao achei {env_file}.")
    else:
        arquivos = _envs_ate_a_raiz(Path.cwd())

    for env in arquivos:
        if _rastreado_pelo_git(env):
            raise Erro(
                f"{env} esta rastreado pelo git. Rode:\n\n"
                f"  git rm --cached {env}\n\n"
                "confira que .env esta no .gitignore, e rode o deploy de novo."
            )
        cfg.update(_chaves_no_env(env, CHAVES))
    cfg["_origens"] = [str(a) for a in arquivos]
    cfg.update({k: os.environ[k] for k in CHAVES if os.environ.get(k)})

    if exigir_credenciais:
        faltando = [k for k in ("CPANEL_HOST", "CPANEL_USER", "CPANEL_TOKEN")
                    if not cfg.get(k)]
        if faltando:
            onde = ("\nLi: " + ", ".join(cfg["_origens"]) if cfg["_origens"]
                    else "\nNao achei nenhum .env daqui para cima.")
            raise Erro(
                f"falta {', '.join(faltando)}.{onde}\n\n"
                "A credencial do cPanel vai UMA VEZ no .env da pasta do "
                "projeto, e serve para todos os clientes. Cada cliente so "
                "precisa de DEPLOY_PATH e SITE_URL no .env da pasta dele."
            )
    cfg["CPANEL_HOST"] = limpar_host(cfg.get("CPANEL_HOST", ""))
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
        # O cPanel da HostGator fica atras do Cloudflare, que recusa requisicao
        # SEM User-Agent com 403 e "error code: 1010" - antes de olhar o token.
        # Sem este header o deploy nunca funcionou, e o 403 parecia problema de
        # permissao: a requisicao sem autenticacao nenhuma da o mesmo erro.
        req.add_header("User-Agent", UA_NAVEGADOR)
        try:
            with urllib.request.urlopen(req, timeout=120,
                                        context=self.ctx) as r:
                bruto = r.read()
        except urllib.error.HTTPError as e:
            corpo = e.read()[:300].decode("utf-8", "replace").strip()
            if "1010" in corpo:
                raise Erro(
                    "o Cloudflare da hospedagem bloqueou a requisicao (403, "
                    "error code 1010). Isto NAO e problema de token: e falta "
                    "de User-Agent, que este script envia. Se apareceu mesmo "
                    "assim, a hospedagem esta bloqueando o seu IP."
                ) from None
            if e.code in (401, 403):
                raise Erro(
                    f"o cPanel recusou a autenticacao (HTTP {e.code}). "
                    "Confira usuario e token, e se o token tem permissao de "
                    f"File Manager.\nResposta do servidor: {corpo[:160]}"
                ) from None
            raise Erro(f"HTTP {e.code} do cPanel: {corpo[:160]}") from None
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

    def ler(self, pasta: str, arquivo: str) -> dict:
        return self.chamar("Fileman", "get_file_content", dir=pasta, file=arquivo)

    def dominios(self) -> dict:
        return self.chamar("DomainInfo", "domains_data")


    def enviar(self, pasta_remota: str, arquivo: Path, nome: str) -> dict:
        # `overwrite=1` e obrigatorio: sem ele o cPanel recusa arquivo que ja
        # existe com "O arquivo para carregamento ja existe", e portanto TODO
        # segundo deploy de um cliente falharia - que e a operacao mais comum
        # da skill, republicar depois de um ajuste.
        #
        # Sobrescrever so e seguro por causa da guarda de outro_negocio(), que
        # roda antes e impede pisar no site de outro cliente.
        corpo, tipo = corpo_multipart(
            {"dir": pasta_remota, "overwrite": "1"},
            "file-1", nome, arquivo.read_bytes())
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



def imagens_pesadas(arquivos):
    return [(rel, p.stat().st_size) for p, rel in arquivos
            if p.suffix.lower() in EXT_IMAGEM and p.stat().st_size > LIMITE_IMAGEM]


def titulo_remoto(cp, pasta: str, listagem: dict):
    """<title> do index.html que JA esta na pasta remota. None se nao houver."""
    dados = listagem.get("data") or []
    nomes = {i.get("file") for i in dados if isinstance(i, dict)}
    if "index.html" not in nomes:
        return None
    r = cp.ler(pasta, "index.html")
    if not status_do_topo(r):
        return None
    return titulo_de((r.get("data") or {}).get("content", "") or "")


def outro_negocio(titulo_la, titulo_novo) -> bool:
    """A pasta ja tem o site de OUTRO cliente.

    Uma conta de cPanel atende a carteira inteira, e um DEPLOY_PATH copiado de
    outro cliente sobrescreve o site dele sem avisar. Com tres clientes voce
    percebe; com trinta, nao.

    Titulo igual = republicacao do mesmo site. Sem titulo dos dois lados = nao
    da para afirmar nada, entao deixa passar: travar por duvida atrapalha mais
    do que ajuda.
    """
    if not titulo_la or not titulo_novo:
        return False
    return titulo_la.strip() != titulo_novo.strip()


def ler_dominios(resposta) -> list:
    """[(dominio, documentroot, tipo)] do que a conta realmente tem."""
    d = (resposta or {}).get("data") or {}
    saida = []
    md = d.get("main_domain") or {}
    if md.get("domain"):
        saida.append((md["domain"], md.get("documentroot", ""), "principal"))
    for chave, tipo in (("addon_domains", "addon"),
                        ("sub_domains", "subdominio"),
                        ("parked_domains", "estacionado")):
        for a in (d.get(chave) or []):
            if isinstance(a, dict) and a.get("domain"):
                saida.append((a["domain"], a.get("documentroot", ""), tipo))
    return saida


def caminho_do_dominio(dominios: list, alvo: str, usuario: str):
    """DEPLOY_PATH de um dominio da conta. None se ele nao estiver la.

    Vale mais que perguntar ao usuario: o cPanel sabe o document root exato de
    cada dominio. E "esse dominio nem esta na conta" e a resposta mais
    importante das tres, porque nenhuma pasta serve enquanto isso for verdade.
    """
    alvo = limpar_host(alvo).lower()
    if alvo.startswith("www."):
        alvo = alvo[4:]
    for dominio, raiz, _tipo in dominios:
        atual = dominio.lower()
        if atual.startswith("www."):
            atual = atual[4:]
        if atual == alvo:
            prefixo = f"/home2/{usuario}/"     # vira relativo a home
            return raiz[len(prefixo):] if raiz.startswith(prefixo) else raiz
    return None


def pasta_inexistente(resposta) -> bool:
    """A listagem falhou porque a pasta nao existe (e nao por outro motivo)."""
    msg = erros_de(resposta).lower()
    return "does not exist" in msg or "nao existe" in msg or "não existe" in msg


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
    # User-Agent de navegador de verdade, nao "deploy-cpanel": o mod_security
    # da HostGator devolve 406 para UA curto ou generico. Com o nome do script
    # esta checagem daria "o site caiu" com o site no ar.
    req = urllib.request.Request(url, headers={"User-Agent": UA_NAVEGADOR})
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

def listar_dominios(cfg: dict, inseguro=False, procurar=None) -> int:
    """Mostra o que a conta TEM, para ninguem escolher DEPLOY_PATH no escuro.

    Perguntar "qual e a pasta?" e perguntar uma coisa que o servidor sabe
    responder. Pior: quando o dominio nem esta na conta, toda opcao que se
    ofereceria esta errada, e so o cPanel pode dizer isso.
    """
    cp = Cpanel(cfg, inseguro=inseguro)
    r = cp.dominios()
    if not status_do_topo(r):
        raise Erro(f"nao consegui listar os dominios: {erros_de(r)}")
    doms = ler_dominios(r)
    usuario = cfg["CPANEL_USER"]

    print()
    print(f"{len(doms)} dominio(s) nesta conta:")
    print()
    for dominio, raiz, tipo in doms:
        curto = caminho_do_dominio([(dominio, raiz, tipo)], dominio, usuario)
        print(f"  {dominio}")
        print(f"     {tipo:<12} DEPLOY_PATH={curto}")

    if not procurar:
        print()
        print("Cliente novo, sem dominio proprio ainda: subpasta do principal.")
        print("  DEPLOY_PATH=public_html/<nome-do-cliente>")
        return 0

    achado = caminho_do_dominio(doms, procurar, usuario)
    if achado:
        print()
        print(f"'{procurar}' esta na conta.")
        print(f"  DEPLOY_PATH={achado}")
        return 0

    curto = limpar_host(procurar)
    if curto.startswith("www."):
        curto = curto[4:]
    print()
    print(f"'{procurar}' NAO esta nesta conta cPanel.")
    print()
    print("Entao nem public_html nem addon domain servem ainda. Uma das duas:")
    print()
    print("  1. adicione como addon domain no cPanel, com o document root FORA")
    print("     do public_html, e use o caminho que ele mostrar")
    print("  2. publique numa subpasta enquanto o dominio nao aponta para ca:")
    print(f"     DEPLOY_PATH=public_html/{curto.split('.')[0]}")
    return 1


def deploy(cfg: dict, dry_run=False, inseguro=False, forcar=False) -> int:
    origem = Path(cfg["SOURCE_DIR"])
    if not origem.is_dir():
        raise Erro(f"a pasta {origem} nao existe - gere o site em dist/ antes.")
    arquivos = arquivos_para_enviar(origem)
    if not arquivos:
        raise Erro(f"{origem} esta vazia.")

    # <title> do que vai subir. Serve duas vezes: antes, para nao pisar no site
    # de outro cliente; depois, para conferir se a home publicada e esta.
    index = origem / "index.html"
    marca_nova = (titulo_de(index.read_text(encoding="utf-8", errors="replace"))
                  if index.exists() else None)

    destino = cfg["DEPLOY_PATH"]
    # em --dry-run as credenciais podem nem existir: nada aqui abre conexao
    quem = cfg.get("CPANEL_USER") or "(usuario nao configurado)"
    onde = cfg.get("CPANEL_HOST") or "(host nao configurado)"
    print(f"Destino: {quem}@{onde}:{cfg['CPANEL_PORT']}/{destino}")
    print(f"Origem:  {origem}  ({len(arquivos)} arquivos)")

    for rel, tamanho in imagens_pesadas(arquivos):
        print(f"aviso: {rel} tem {tamanho // 1024} KB. Acima de "
              f"{LIMITE_IMAGEM // 1024} KB o site fica lento no 4G - comprima "
              "antes de subir.")

    if dry_run:
        print("Modo:    dry-run (nada sera enviado)\n")
        for _, rel in arquivos:
            print(f"  upload {rel}")
        print(f"\n{len(arquivos)} arquivos seriam enviados.")
        return 0

    cp = Cpanel(cfg, inseguro=inseguro)

    # Pasta de cliente novo ainda nao existe, e isso nao e erro: o
    # Fileman::upload_files cria a arvore sozinho, inclusive aninhada. Testado
    # contra uma HostGator real.
    #
    # Nao ha mkdir aqui de proposito: `Fileman::mkdir` NAO EXISTE nesta versao
    # do cPanel (nem create_directory, nem makedir). O script bash antigo
    # chamava mkdir e portanto nunca teria criado pasta nenhuma.
    listagem = cp.listar(destino)
    if not status_do_topo(listagem):
        if not pasta_inexistente(listagem):
            raise Erro(
                f"nao consegui listar {destino}: {erros_de(listagem)}\n"
                "Confira host, usuario, token e porta 2083."
            )
        print(f"{destino} ainda nao existe. O upload cria.")
        listagem = {"status": 1, "data": []}
    conflitos = indices_conflitantes(listagem)
    if conflitos:
        print(f"\naviso: {destino} ja tem {', '.join(conflitos)}. O Apache "
              "serve esse arquivo antes do index.html novo, entao a home velha "
              "continua no ar mesmo com o deploy dando certo. Apague pelo "
              "Gerenciador de Arquivos do cPanel.\n")

    # O site de outro cliente ja esta nesta pasta? Uma conta atende a carteira
    # inteira, e DEPLOY_PATH copiado de outro cliente sobrescreve o site dele
    # em silencio.
    if not forcar:
        la = titulo_remoto(cp, destino, listagem)
        if outro_negocio(la, marca_nova):
            raise Erro(
                f"{destino} ja tem um site publicado, e nao e este:\n\n"
                f"  no servidor: {la}\n"
                f"  vai subir:   {marca_nova}\n\n"
                "Se DEPLOY_PATH foi copiado do .env de outro cliente, corrija. "
                "Se a troca e proposital, rode de novo com --forcar."
            )

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
    ok, recado = conferir_publicado(url, marca_nova, inseguro=inseguro)
    print(("\n✅ " if ok else "\n⚠️  ") + recado)
    if ok:
        print("Abra no celular e confira antes de avisar o cliente.")
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

    # ── o cPanel sabe onde cada dominio mora: nao se pergunta ao usuario ────
    # Uma sessao perguntou "public_html ou addon domain?" e ofereceu as duas,
    # com o dominio nem estando na conta. As duas respostas estavam erradas.
    resp = {"status": 1, "data": {
        "main_domain": {"domain": "agencia.com.br",
                        "documentroot": "/home2/u1/public_html"},
        "addon_domains": [{"domain": "padaria.com.br",
                           "documentroot": "/home2/u1/clientes/padaria"}],
        "sub_domains": [], "parked_domains": []}}
    doms = ler_dominios(resp)
    assert len(doms) == 2 and doms[0][2] == "principal", doms
    assert ("padaria.com.br", "/home2/u1/clientes/padaria", "addon") in doms

    # o caminho vira relativo a home, que e o que DEPLOY_PATH espera
    assert caminho_do_dominio(doms, "agencia.com.br", "u1") == "public_html"
    assert caminho_do_dominio(doms, "padaria.com.br", "u1") == "clientes/padaria"
    # www e https:// no que o usuario digita nao podem atrapalhar
    assert caminho_do_dominio(doms, "www.padaria.com.br", "u1") == "clientes/padaria"
    assert caminho_do_dominio(doms, "https://padaria.com.br/", "u1") == "clientes/padaria"
    # o caso real: dominio fora da conta -> None, nunca um chute
    assert caminho_do_dominio(doms, "clstellafernandes.com.br", "u1") is None
    # docroot fora da home volta inteiro, sem cortar errado
    assert caminho_do_dominio([("x.com", "/var/www/x", "addon")], "x.com", "u1") \
        == "/var/www/x"
    assert ler_dominios({"status": 1, "data": {}}) == []
    assert ler_dominios({}) == []

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

    # ── nao pisar no site de outro cliente ──────────────────────────────────
    # Uma conta de cPanel atende a carteira inteira; DEPLOY_PATH copiado do
    # .env de outro cliente sobrescreve o site dele em silencio.
    assert outro_negocio("Padaria Sao Jose em Caico", "Oficina do Ze em Natal")
    assert not outro_negocio("Padaria Sao Jose", "Padaria Sao Jose")
    assert not outro_negocio("  Padaria  ", "Padaria")      # so espaco
    assert not outro_negocio(None, "Qualquer"), "pasta vazia nao trava"
    assert not outro_negocio("Algum site", None), "sem title, nao da para afirmar"

    class _CpLeitor:
        def __init__(self, conteudo): self.c = conteudo
        def ler(self, pasta, arq):
            return {"status": 1, "data": {"content": self.c}}
    lista_com = {"status": 1, "data": [{"file": "index.html"}, {"file": "css"}]}
    lista_sem = {"status": 1, "data": [{"file": "leiame.txt"}]}
    cp_l = _CpLeitor("<html><head><title>Oficina do Ze</title></head>")
    assert titulo_remoto(cp_l, "public_html/x", lista_com) == "Oficina do Ze"
    assert titulo_remoto(cp_l, "public_html/x", lista_sem) is None
    assert titulo_remoto(cp_l, "public_html/x", {"status": 1, "data": []}) is None

    # ── a verificacao final usa UA de navegador, nao o nome do script ───────
    # mod_security da HostGator devolve 406 para UA curto: com "deploy-cpanel"
    # a checagem diria "o site caiu" com o site no ar.
    import inspect as _i
    assert "UA_NAVEGADOR" in _i.getsource(conferir_publicado),         "UA curto faz o mod_security devolver 406"

    # ── pasta de cliente novo ainda nao existe: criar faz parte do fluxo ────
    naoexiste = {"status": 0, "errors":
                 ['The directory “/home2/u/public_html/x” does not exist.']}
    assert pasta_inexistente(naoexiste)
    assert not pasta_inexistente({"status": 0, "errors": ["Access denied"]})
    assert not pasta_inexistente({"status": 1, "data": []})

    # Nao se cria pasta em lugar nenhum: o upload_files faz isso sozinho,
    # aninhada inclusive. Testado contra uma HostGator real. Se alguem trouxer
    # de volta um passo de mkdir, ele vai falhar em producao, porque
    # Fileman::mkdir NAO EXISTE nesta versao do cPanel.
    assert not hasattr(Cpanel, "criar_pasta"),         "o cPanel da HostGator nao tem Fileman::mkdir; o upload cria a pasta"

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

    # overwrite=1 tem que chegar no corpo: sem ele o cPanel recusa arquivo que
    # ja existe, e TODO segundo deploy de um cliente falharia. Republicar
    # depois de um ajuste e a operacao mais comum que existe.
    import inspect as _ins
    assert '"overwrite": "1"' in _ins.getsource(Cpanel.enviar), \
        "sem overwrite=1 o redeploy falha em todos os arquivos"
    corpo_ow, _t = corpo_multipart({"dir": "d", "overwrite": "1"}, "file-1",
                                   "x.html", b"oi")
    assert b'name="overwrite"\r\n\r\n1\r\n' in corpo_ow

    tmp = Path(tempfile.mkdtemp(prefix="lsl-teste-"))
    try:
        # ── .env: BOM e a chave vizinha ─────────────────────────────────────
        env = tmp / ".env"
        env.write_text("CPANEL_HOST=meusite.com.br\nCPANEL_USER=u1\n"
                       "CPANEL_TOKEN=tok123\n"
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


        pesadas = imagens_pesadas(arquivos)
        assert [r for r, _ in pesadas] == ["img/foto.jpg"], pesadas

        # ── .env versionado trava o deploy ──────────────────────────────────
        assert _rastreado_pelo_git(tmp / "nao-existe.env") is False

        # ── o Cloudflare da HostGator exige User-Agent ──────────────────────
        # Sem ele: 403 "error code: 1010", identico com ou sem token. O deploy
        # nunca funcionou e o erro parecia problema de permissao.
        assert UA_NAVEGADOR.startswith("Mozilla/")
        class _Falso:
            def __init__(self): self.headers = {}
            def add_header(self, k, v): self.headers[k.lower()] = v
        falso = _Falso()
        alvo_cp = Cpanel.__new__(Cpanel)
        alvo_cp._auth = "cpanel u:t"
        try:
            Cpanel._abrir(alvo_cp, falso)
        except Exception:
            pass                      # nao ha servidor: so os headers importam
        assert falso.headers.get("user-agent", "").startswith("Mozilla/"),             "sem User-Agent a HostGator devolve 403 antes de olhar o token"
        assert falso.headers.get("authorization") == "cpanel u:t"

        # ── o host aceita ser colado como URL do painel ─────────────────────
        # Todo mundo cola "https://x.meusitehostgator.com.br/" do navegador.
        # Sem limpar, o script monta https://https://dominio/:2083 e quebra.
        for bruto, limpo in [
            ("https://abc.meusitehostgator.com.br/", "abc.meusitehostgator.com.br"),
            ("http://meusite.com.br", "meusite.com.br"),
            ("meusite.com.br", "meusite.com.br"),
            ("https://meusite.com.br:2083/cpsess123/frontend/", "meusite.com.br"),
            ("  meusite.com.br/  ", "meusite.com.br"),
            ("", ""),
        ]:
            assert limpar_host(bruto) == limpo, (bruto, limpar_host(bruto))

        # ── uma conta de hospedagem, varios clientes ────────────────────────
        # Credencial uma vez na raiz do projeto; cada cliente diz so o destino.
        # Sem isto, cada cliente precisaria de uma copia do token em disco.
        # pasta propria: o tmp acima ja tem um .env do teste de BOM, e ele
        # apareceria na busca para cima
        raiz = Path(tempfile.mkdtemp(prefix="lsl-projeto-"))
        cliente = raiz / "clientes" / "padaria"
        cliente.mkdir(parents=True)
        (raiz / ".env").write_text(
            "CPANEL_HOST=meuservidor.com.br\nCPANEL_USER=agencia\n"
            "CPANEL_TOKEN=token-da-conta\n", encoding="utf-8")
        (cliente / ".env").write_text(
            "DEPLOY_PATH=public_html/padaria\n"
            "SITE_URL=https://meuservidor.com.br/padaria\n", encoding="utf-8")
        antes = os.getcwd()
        try:
            os.chdir(cliente)
            cfg = carregar_config()
            assert cfg["CPANEL_TOKEN"] == "token-da-conta", "herdou da raiz"
            assert cfg["CPANEL_USER"] == "agencia"
            assert cfg["DEPLOY_PATH"] == "public_html/padaria", cfg["DEPLOY_PATH"]
            assert cfg["SITE_URL"].endswith("/padaria")
            # a conta e lida PRIMEIRO e o cliente DEPOIS: e essa ordem que faz
            # o destino do cliente ganhar sem apagar a credencial da conta
            assert cfg["_origens"] == [str(raiz / ".env"),
                                       str(cliente / ".env")], cfg["_origens"]

            # segundo cliente na mesma conta, destino proprio
            outro = raiz / "clientes" / "oficina"
            outro.mkdir()
            (outro / ".env").write_text("DEPLOY_PATH=public_html/oficina\n",
                                        encoding="utf-8")
            os.chdir(outro)
            c2 = carregar_config()
            assert c2["CPANEL_TOKEN"] == "token-da-conta", "mesma conta"
            assert c2["DEPLOY_PATH"] == "public_html/oficina", c2["DEPLOY_PATH"]

            # --env forca um arquivo so e ignora a busca para cima
            so_um = carregar_config(cliente / ".env", exigir_credenciais=False)
            assert not so_um.get("CPANEL_TOKEN"), "com --env nao sobe a arvore"
        finally:
            os.chdir(antes)
            shutil.rmtree(raiz, ignore_errors=True)

        # ── --dry-run nao abre conexao, entao nao pede credencial ───────────
        # Descoberto construindo um site de verdade: dar --dry-run para ver o
        # lote exigia ter o cPanel em maos, sem precisar de nada disso.
        cfg = carregar_config(tmp / "nao-existe.env", exigir_credenciais=False)
        assert cfg["DEPLOY_PATH"] == "public_html" and cfg["SOURCE_DIR"] == "dist"
        # --env apontando para arquivo que nao existe: diz isso, nao outra coisa
        try:
            carregar_config(tmp / "nao-existe.env")
            raise AssertionError("--env inexistente tinha que parar")
        except Erro as e:
            assert "nao achei" in str(e), e
        # sem credencial nenhuma, a mensagem tem que ensinar o modelo de conta
        vazia = Path(tempfile.mkdtemp(prefix="lsl-vazio-"))
        antes2 = os.getcwd()
        try:
            os.chdir(vazia)
            carregar_config()
            raise AssertionError("deploy real sem credencial tinha que parar")
        except Erro as e:
            assert "CPANEL_HOST" in str(e) and "todos os clientes" in str(e), e
        finally:
            os.chdir(antes2)
            shutil.rmtree(vazia, ignore_errors=True)

        # ── o ambiente ganha do arquivo, para CI nao gravar segredo em disco ─
        os.environ["CPANEL_TOKEN"] = "do-ambiente"
        try:
            cfg = carregar_config(env)          # env tem CPANEL_TOKEN=tok123
            assert cfg["CPANEL_TOKEN"] == "do-ambiente", cfg["CPANEL_TOKEN"]
            assert cfg["CPANEL_HOST"] == "meusite.com.br", "o .env ainda vale"
        finally:
            del os.environ["CPANEL_TOKEN"]
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
    p.add_argument("comando", nargs="?", choices=["dominios"],
                   help="dominios: lista os dominios da conta e onde cada um "
                        "mora. Rode ANTES de escolher DEPLOY_PATH")
    p.add_argument("--dominio", help="com `dominios`: procura este dominio e "
                                     "diz o DEPLOY_PATH dele")
    p.add_argument("--env", default=None,
                   help="usa SO este arquivo, em vez de juntar os .env das "
                        "pastas acima")
    p.add_argument("--dry-run", action="store_true",
                   help="mostra o que subiria, sem enviar nada")
    p.add_argument("--inseguro", action="store_true",
                   help="nao verifica o certificado do cPanel. O TOKEN VIAJA "
                        "NESSA CONEXAO: use so quando o erro for de certificado "
                        "do servidor compartilhado, nunca em rede publica")
    p.add_argument("--forcar", action="store_true",
                   help="publica mesmo que a pasta remota ja tenha o site de "
                        "outro negocio")
    p.add_argument("--autoteste", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.autoteste:
        autoteste()
        return 0
    if args.inseguro:
        print("aviso: verificacao de certificado desligada. O token viaja "
              "nessa conexao.\n", file=sys.stderr)
    # `dominios` abre conexao, entao precisa de credencial mesmo com --dry-run
    cfg = carregar_config(args.env,
                          exigir_credenciais=bool(args.comando) or not args.dry_run)
    if cfg["_origens"]:
        print("config: " + " + ".join(cfg["_origens"]))
    if args.comando == "dominios":
        return listar_dominios(cfg, args.inseguro, args.dominio)
    return deploy(cfg, dry_run=args.dry_run, inseguro=args.inseguro,
                  forcar=args.forcar)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Erro as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
