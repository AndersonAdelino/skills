# HostGator cPanel

Como esta skill publica o `dist/` no plano compartilhado (plano M e equivalentes com cPanel). Leia antes de qualquer deploy.

## O que o plano aguenta

Plano M da HostGator Brasil traz cPanel, SSH, FTP, SSL, vários domínios e `public_html`. Sirva HTML/CSS/JS estático (e PHP simples, se um dia precisar). Não publique Next, React em modo server ou processo Node.

O nome certo da credencial é **API Token**, não "API key". Nasce em cPanel → Segurança → Gerenciar tokens de API. O valor aparece uma vez. Trata como senha.

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

`scripts/deploy-cpanel.py` usa UAPI com header:

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
4. cria pastas remotas com `Fileman::mkdir`, pai antes de filho
5. envia cada arquivo de `SOURCE_DIR` com `Fileman::upload_files`
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
