---
name: cpanel-deploy
description: Publica uma pasta de site estático num cPanel (HostGator e equivalentes) via API, com token no .env, e confere no fim se o endereço no ar é mesmo a página nova. Ativa em "sobe no cPanel", "publica no HostGator", "deploy no public_html", "manda o dist pro servidor", "coloca o site no ar", "atualiza o site do cliente", "publica essa pasta", "deploy to cPanel", "upload to public_html". Serve qualquer pasta pronta — feita à mão, por outra skill, ou saída de Hugo, Astro, Vite, Eleventy. NÃO use para hospedagem que não seja cPanel (Vercel, Netlify, S3, FTP puro), nem para aplicação que precise de servidor rodando (Next em modo server, Node, PHP dinâmico, WordPress) — este script só copia arquivos. Se não houver uma pasta pronta para publicar, o trabalho é construir o site primeiro.
argument-hint: [--dry-run] [--forcar]
license: MIT
---

# cPanel Deploy

Pega uma pasta de arquivos estáticos e põe num cPanel. Python puro, sem
`pip install`, sem FTP, sem CI.

No fim ele **busca o endereço público e confere se a página no ar é a que
subiu**, comparando o `<title>`. Deploy que "deu certo" e serve o site velho é
o modo de falha mais comum aqui, e o script existe em boa parte para pegá-lo.

---

## Config: duas camadas

O caso normal não é um site: é uma conta de hospedagem atendendo vários
clientes. Então a credencial fica num lugar e o destino em outro.

```
projeto/
├── .env                          <- A CONTA. Uma vez, para todos.
│                                    CPANEL_HOST, CPANEL_USER, CPANEL_TOKEN
└── clientes/
    ├── padaria/
    │   ├── .env                  <- DEPLOY_PATH, SITE_URL
    │   └── dist/
    └── oficina/
        ├── .env
        └── dist/
```

O script sobe até 4 pastas juntando os `.env`, do mais distante para o mais
próximo, então **o do cliente ganha**. Rode de dentro da pasta do cliente.

| Chave | Onde | O que é |
|---|---|---|
| `CPANEL_HOST` | conta | o hostname do painel. Pode colar a URL inteira, o script limpa |
| `CPANEL_USER` | conta | usuário do cPanel (`ande9564`), **não** o e-mail da conta |
| `CPANEL_TOKEN` | conta | cPanel → Segurança → Gerenciar tokens de API |
| `CPANEL_PORT` | conta | 2083, o padrão |
| `DEPLOY_PATH` | cliente | pasta remota. **Uma por cliente** |
| `SOURCE_DIR` | cliente | pasta local, `dist` por padrão |
| `SITE_URL` | cliente | endereço público, para a conferência final |

`--env arquivo` força um arquivo só e desliga a busca para cima.

Modelo em `assets/env.example`. Detalhes de HostGator, limites de plano e
segurança de conta compartilhada em `references/hostgator.md` — **leia antes
do primeiro deploy**.

---

## Como usar

```bash
cd clientes/padaria

python <SKILL>/scripts/deploy-cpanel.py --dry-run   # lista, sem conexão
python <SKILL>/scripts/deploy-cpanel.py             # publica
```

Sempre `--dry-run` primeiro. Ele não abre conexão nenhuma e por isso nem pede
credencial: serve para conferir o lote e o destino antes de tocar no servidor.

---

## O que ele faz sozinho

| Checagem | Por quê |
|---|---|
| Recusa se o `.env` estiver no git | token commitado é irreversível: quem clonou já tem |
| Lê **só** as chaves do cPanel, nunca o `.env` inteiro | o `.env` do cliente costuma ter credencial de outra coisa |
| **Para se a pasta remota já tiver o site de outro negócio** | `DEPLOY_PATH` copiado de outro cliente sobrescreve o site dele em silêncio. Compara o `<title>` remoto com o que vai subir. `--forcar` passa por cima |
| Avisa se houver `index.php` na pasta | o Apache serve ele antes do `index.html` novo, e a home velha fica no ar |
| Avisa imagem acima de 500 KB | o site abre no 4G |
| Lê o JSON de verdade, topo e por arquivo separados | ver abaixo |
| **Busca a URL publicada e compara o `<title>`** | é a única checagem que responde "subiu mesmo?" |

O token nunca é impresso, e não vai por linha de comando: só no header da
requisição, porque argumento de processo aparece em `ps aux`.

Se a conferência final falhar, o script sai com código 1. **Não anuncie "site
no ar" antes do ✅.**

---

## Coisas que só se descobre publicando

Tudo abaixo foi encontrado contra uma HostGator real, e cada uma tem teste.

**O Cloudflare recusa requisição sem `User-Agent`.** Devolve 403 com
`error code: 1010`, antes de olhar o token — requisição sem autenticação
nenhuma dá o mesmo erro. Sem esse header o deploy nunca funciona, e o 403
parece problema de permissão. O script manda o header e, se o 1010 aparecer
mesmo assim, diz explicitamente que não é o token.

**`Fileman::mkdir` não existe** nesta versão do cPanel (nem `create_directory`,
nem `makedir`). Não faz falta: o `upload_files` cria a árvore sozinho, aninhada
inclusive.

**`upload_files` recusa sobrescrever sem `overwrite=1`.** Sem ele, o segundo
deploy de um cliente falha em todos os arquivos, que é a operação mais comum.

**O `status` do UAPI não pode ser lido por busca de texto.** `upload_files`
devolve um status **por arquivo dentro de `data`**, então uma resposta de erro
pode conter `"status":1` aninhado:

```json
{"errors":["token invalido"],"status":0,"data":[{"file":"a.jpg","status":1}]}
```

Ler isso com `grep '"status":1'` reporta sucesso sem ter subido nada. Os dois
status importam e são coisas diferentes: o de cima diz se a chamada foi aceita,
o de baixo se aquele arquivo entrou.

**O mod_security devolve 406 para User-Agent curto.** Navegador nunca cai
nisso, mas monitor de uptime e crawler simples caem, e acusam o site como fora
do ar. A conferência final usa UA de navegador por causa disso.

---

## Antes do deploy

- `.env` existe, está no `.gitignore` e não foi commitado
- `DEPLOY_PATH` é a pasta **deste** cliente
- o conteúdo atual é sobrescrito arquivo a arquivo. **O script não apaga nada**:
  lixo de instalador antigo continua lá até você limpar pelo cPanel
- em addon domain, `DEPLOY_PATH` é o document root que o cPanel mostrar, não
  `public_html`

## Teste

```bash
python scripts/deploy-cpanel.py --autoteste
```

Sem rede, sem chave, sem tocar em servidor. Roda no CI a cada push.
