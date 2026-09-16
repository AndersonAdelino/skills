# HostGator cPanel

Como a skill cpanel-deploy publica no plano compartilhado (plano M e equivalentes com cPanel). Leia antes de qualquer deploy.

## Quantos clientes cabem

Medido com um site desta família: **13 inodes e 420 KB**.

| Limite do Plano M | Teto | Observação |
|---|---|---|
| **"Crie +60 sites"** (página de vendas) | **60** | é o teto que vale. A página de suporte diz "domínios ilimitados" e contradiz |
| 250 mil inodes | ~19.000 sites | nunca vai ser o gargalo |
| 100 GB | ~249.000 sites | 60 sites = 25 MB, 0,025% do plano |
| **120 mil visitas/mês** | somadas na conta | 60 clientes → 2.000 cada. **Este é o limite real** |
| 25 processos simultâneos | da conta toda | estático libera rápido, mas é compartilhado |

Espaço nunca é o problema. O que pega é **visitas somadas** e o teto de 60.
Para vitrine de comércio local, 120 mil/mês atende bem uns 20 a 40 clientes.
O Turbo sobe para 400 mil e 150 sites.

**"Site" no cPanel normalmente é domínio adicional.** Subpasta do
`public_html` tende a não consumir a cota, mas confirme com o suporte: a
resposta muda seu planejamento comercial.

## Segurança de conta compartilhada

**Uma conta cPanel não isola os domínios entre si.** Todos rodam como o mesmo
usuário Unix, na mesma árvore. Site comprometido = leitura e escrita em todos
os outros da conta. Isso é como o cPanel funciona, não configuração.

O que torna o modelo aceitável é uma coisa só:

> **Zero PHP na conta.** Nenhum WordPress, nenhum formulário PHP, nenhum
> script dinâmico, em nenhum cliente.

A contaminação cruzada clássica é sempre a mesma história: plugin
desatualizado → shell PHP → todos os sites da conta. Sem PHP rodando, esse
vetor não existe; HTML não executa nada. **No dia em que um cliente ganhar
"só um formulariozinho", o isolamento dos outros vai junto.**

O que sobra, e não tem correção dentro de uma conta só:

| | |
|---|---|
| Um token, todos os clientes | token de cPanel é escopo de conta, não existe por diretório |
| Conta suspensa derruba todos | mitigue guardando o `dist/` de cada cliente localmente |
| IP compartilhado | um cliente marcado afeta a reputação dos outros |

Isolamento de verdade exige **uma conta cPanel por cliente**, o que custa mais.

## Cada cliente na sua pasta, fora do public_html

Se o site do cliente ficar em `public_html/cliente`, ele responde em **dois
endereços**: o domínio dele e `seudominio.com.br/cliente`. Isso é conteúdo
duplicado para o Google, e expõe a lista da sua carteira — dá para adivinhar
`/padaria`, `/oficina` e ver os sites dos outros.

Ao criar o addon domain, aponte o document root para **fora** do `public_html`:

```
/home2/SEU_USUARIO/clientes/nomedocliente
```

O `DEPLOY_PATH` do `.env` daquele cliente vira esse caminho e o script funciona
igual. Aí o site só responde pelo domínio dele.

## O que o plano aguenta

Plano M da HostGator Brasil traz cPanel, SSH, FTP, SSL, vários domínios e `public_html`. Sirva **apenas** HTML/CSS/JS estático. Não publique Next, React em modo
server nem processo Node — e, se a conta atende vários clientes, **nada de PHP
em cliente nenhum**: o motivo está em "Segurança de conta compartilhada", acima.

O nome certo da credencial é **API Token**, não "API key". Nasce em cPanel → Segurança → Gerenciar tokens de API. O valor aparece uma vez. Trata como senha.

## Uma conta, vários clientes

O caso normal de quem usa esta skill não é um site: é uma conta de hospedagem
atendendo a carteira inteira. Então a configuração é em duas camadas.

```
projeto/
├── .env                          <- A CONTA. Uma vez, para todos.
│                                    CPANEL_HOST, CPANEL_USER, CPANEL_TOKEN
└── clientes/
    ├── padaria/
    │   ├── .env                  <- O DESTINO deste cliente.
    │   │                            DEPLOY_PATH, SITE_URL
    │   └── dist/
    └── oficina/
        ├── .env                  <- DEPLOY_PATH=public_html/oficina
        └── dist/
```

O script sobe até 4 pastas procurando `.env` e junta todos, **do mais distante
para o mais próximo**. O do cliente é lido por último, então ele ganha: pode
sobrescrever qualquer coisa, inclusive a conta, se um cliente tiver hospedagem
própria.

Rode o deploy de dentro da pasta do cliente. O token fica num lugar só, em vez
de uma cópia por pasta.

Se um cliente precisar de credencial isolada, `--env caminho/do/.env` força um
arquivo único e desliga a busca para cima.

### Onde cada cliente vai parar no servidor

| Situação | `DEPLOY_PATH` | `SITE_URL` |
|---|---|---|
| Subpasta do seu domínio | `public_html/padaria` | `https://seudominio.com.br/padaria` |
| Addon domain do cliente | o document root que o cPanel mostrar | `https://dominiodocliente.com.br` |
| Domínio principal da conta | `public_html` | `https://seudominio.com.br` |

**Uma pasta por cliente.** Se dois apontarem para o mesmo lugar, o segundo
deploy sobrescreveria o primeiro. O script compara o `<title>` que já está no
servidor com o que vai subir e **para** se forem sites diferentes; `--forcar`
passa por cima quando a troca é proposital.

`SITE_URL` vazio faz o script conferir `https://CPANEL_HOST`, que para deploy em
subpasta é o endereço errado. Preencha.

## `.env`

Nunca commitar. Nunca imprimir o token. Coloque `.env` no `.gitignore` antes do primeiro deploy.

```
CPANEL_HOST=seudominio.com.br
CPANEL_USER=usuario_cpanel
CPANEL_TOKEN=cole_o_token_aqui
CPANEL_PORT=2083
DEPLOY_PATH=public_html
SOURCE_DIR=dist
SITE_URL=https://seudominio.com.br
```

`SITE_URL` é o endereço público que o script abre no fim para conferir se a home
nova está no ar. Se ficar vazio, ele usa `https://CPANEL_HOST` — o que dá errado
quando o site é um addon domain com host de cPanel diferente do domínio.

Grave o arquivo em UTF-8 **sem BOM**. O script lê como `utf-8-sig` justamente
porque Bloco de Notas e `Out-File -Encoding utf8` gravam BOM no Windows, e aí a
primeira chave do arquivo nunca casaria com o nome.

`CPANEL_HOST` é o hostname que abre o cPanel na porta 2083 (domínio ou servidor). `CPANEL_USER` é o usuário do cPanel, não o e-mail da conta HostGator.

Addon domain aponta para uma pasta. Se o site não for o domínio principal, `DEPLOY_PATH` vira essa pasta (`public_html/oficinax` ou o document root que o cPanel mostrar).

## Como o script publica

O script usa UAPI com header:

```
Authorization: cpanel USUARIO:TOKEN
```

Base:

```
https://HOST:2083/execute/Modulo/funcao
```

Fluxo do script:

1. lê **só as chaves do cPanel** do `.env` — não faz `source`, não exporta o resto
2. recusa seguir se `.env` estiver rastreado pelo git
3. lista `DEPLOY_PATH` e avisa se houver `index.php`/`default.php` lá
4. para se a pasta remota já tiver o site de **outro** negócio
5. envia cada arquivo de `SOURCE_DIR` com `Fileman::upload_files`, que cria a
   árvore de pastas sozinho e precisa de `overwrite=1` para republicar
6. busca a URL publicada e confere se a home nova é a que responde
7. devolve host e caminho — sem ecoar o token

O script sobrescreve arquivos de mesmo nome. **Não esvazia a pasta remota.**

### Por que o status do UAPI não pode ser lido por grep

O `upload_files` devolve um status por arquivo **dentro** de `data`:

```json
{"status":1,"data":{"uploads":[{"file":"a.jpg","status":1}]}}
```

Uma resposta de erro, então, pode ter `status:1` aninhado:

```json
{"errors":["token invalido"],"status":0,"data":[{"file":"a.jpg","status":1}]}
```

A versão anterior deste script decidia sucesso com `grep '"status":1'` na
resposta inteira, e portanto lia a resposta acima como sucesso: imprimia `ok`
para cada arquivo e terminava com "Pronto", sem ter subido nada. O status do
topo e o status por arquivo são coisas diferentes e os dois importam — o de
cima diz se a chamada foi aceita, o de baixo se aquele arquivo entrou.

### `index.php` ganha do `index.html`

Se a pasta tiver lixo de instalador (WordPress abandonado, por exemplo), o
Apache serve `index.php` antes do `index.html` novo. O deploy dá certo e o site
velho continua no ar. O script avisa na listagem inicial e pega de novo na
conferência final, quando o `<title>` da página publicada não bate com o que
subiu. Limpar é manual, pelo Gerenciador de Arquivos do cPanel.

### `--inseguro`

Desliga a verificação do certificado. Em hospedagem compartilhada o cPanel às
vezes responde na porta 2083 com o certificado do servidor, não do domínio, e aí
a verificação falha legitimamente. **O token viaja nessa conexão**: use quando o
erro for esse, nunca em rede pública.

## SSL e domínio

HostGator emite SSL grátis no plano. Depois do upload, abra `https://dominio`. Se o certificado ainda não estiver ativo, espere a emissão ou force HTTPS no `.htaccess` só depois do cadeado aparecer.

## Alternativa SSH

Se UAPI falhar (porta 2083 bloqueada, token sem permissão de File Manager), o plano M tem SSH. Aí o caminho estável é `rsync`/`scp` para `/home/USUARIO/public_html/`. Não coloque senha SSH no `.env` do vídeo. Chave ou token de cPanel.

## Segurança no vídeo e no repo

- token fora de cena
- `.env.example` sem valor real
- deploy primeiro num subdomínio ou addon de teste
- não use token irrestrito em máquina compartilhada sem data de expiração
