# local-site-lift

Pega o site feio de um comércio local, reconstrói em HTML estático e sobe no
cPanel da HostGator com token no `.env`.

O trabalho não é "fazer um site bonito". É colocar o comércio no ar com um
caminho óbvio até o WhatsApp.

```
Melhora o site da Padaria São José em Currais Novos/RN.
WhatsApp 84 99999-1234, abre 6h-19h, fecha domingo, Rua Grande 120, Centro.
Não faz deploy ainda.
```

## O que sai

```
PRODUCT.md        o brief do negócio
ANTES.md          o que o site atual fazia de errado
DESIGN.md         paleta, tipos, conceito de layout — decidido antes do código
dist/             o site: HTML + CSS + JS mínimo + imagens
```

## Instalação

```
npx skills add AndersonAdelino/skills
```

Ou, com o marketplace:

```
/plugin marketplace add AndersonAdelino/skills
/plugin install adelino-skills@adelino
```

## Dependências

**Python 3.** Só isso — o deploy usa a biblioteca padrão, sem `pip install`.
O site que ela gera não precisa de build: é HTML, CSS e um pouco de JS.

Nada de React, Next ou bundler. Hospedagem compartilhada não é lugar disso.

## Deploy

```bash
cp .claude/skills/local-site-lift/assets/env.example .env
# preencha host, usuário e token do cPanel
python .claude/skills/local-site-lift/scripts/deploy-cpanel.py --dry-run
python .claude/skills/local-site-lift/scripts/deploy-cpanel.py
```

Token: cPanel → Segurança → Gerenciar tokens de API. O valor aparece uma vez.
Não grave vídeo com o token na tela.

### O que o deploy confere sozinho

| Checagem | Por quê |
|---|---|
| `.env` não está no git | token commitado é irreversível: quem clonou já tem |
| Lê só as chaves do cPanel, não o `.env` inteiro | o `.env` do cliente costuma ter credencial de outra coisa |
| O cPanel aceitou cada arquivo, lendo o JSON de verdade | ver abaixo |
| Já existe `index.php` na pasta remota | ele ganha do `index.html` novo e deixa a home velha no ar |
| Alguma imagem passa de 500 KB | o site abre no 4G, no sol, com uma mão |
| **A URL publicada abriu e é a home nova** | comparando o `<title>` que subiu com o que a URL responde |

O token nunca é impresso, e não vai por linha de comando — só no header da
requisição, porque argumento de processo aparece em `ps aux`.

### Por que o status do cPanel não pode ser lido por grep

O `upload_files` do UAPI devolve um status **por arquivo, dentro de `data`**.
Então uma resposta de erro pode conter `"status":1` aninhado:

```json
{"errors":["token invalido"],"status":0,"data":[{"file":"a.jpg","status":1}]}
```

A primeira versão deste deploy (em bash) decidia sucesso com
`grep '"status":1'` na resposta inteira, e lia isso como sucesso: imprimia `ok`
para cada arquivo e terminava com "Pronto", sem ter subido nada. As cinco
respostas que quebravam estão fixadas em `--autoteste`.

## O que entra e o que não entra

**Entra:** vitrine de padaria, oficina, clínica, salão, restaurante,
profissional liberal. WhatsApp, mapa, horário, schema `LocalBusiness`.

**Não entra:** tema WordPress, WooCommerce, carrinho, checkout, área logada,
blog com CMS, dashboard, app, Next na Vercel. Isso é outro produto — a skill
diz o limite e oferece só a vitrine.

## Limites conhecidos

- **Não apaga nada no servidor.** Sobrescreve arquivo por arquivo. Lixo de
  instalador antigo continua lá até você limpar pelo cPanel
- **Um arquivo por requisição.** Site com 40 imagens são 40 viagens — funciona,
  mas não é rápido
- **Não gera conteúdo do negócio.** CNPJ, endereço, horário, foto e depoimento
  vêm de você. A skill deixa placeholder explícito em vez de inventar
- **`--inseguro` existe** para o caso de o cPanel responder com o certificado do
  servidor em vez do domínio. O token viaja nessa conexão: só use quando o erro
  for esse

## Teste

```bash
python scripts/deploy-cpanel.py --autoteste
```

Sem rede, sem chave, sem tocar em servidor nenhum. Roda no CI a cada push.

## Licença

MIT.
