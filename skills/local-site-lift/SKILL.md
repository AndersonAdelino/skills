---
name: local-site-lift
description: Refaz site feio de negócio local como HTML estático rápido e publica no cPanel da HostGator com token no .env. Ativa em "melhora o site da padaria", "site feio de comércio", "refaz a vitrine da oficina", "landing page pro meu salão", "site de clínica/restaurante/pet shop/advogado", "sobe no HostGator plano M", "deploy no cPanel", "public_html", "botão de WhatsApp no site", "redesign a local business site", "deploy to cPanel". NÃO use para tema WordPress, loja com carrinho ou checkout, área logada, blog com CMS, dashboard, app, SaaS, painel admin, nem projeto Next/React que precise de servidor — para esses, diga o limite e ofereça só a vitrine estática. Se o pedido for vago como "faz um site", pergunte que negócio é e se tem endereço físico antes de acionar.
argument-hint: <nome do negócio + cidade> [URL do site atual]
license: MIT
---

# Local Site Lift

Transforma site feio de negócio local em página estática rápida, com cara própria, feita para converter no celular, e sobe no cPanel da HostGator.

O trabalho não é "fazer um site bonito". É colocar o comércio no ar com um caminho óbvio até o WhatsApp.

## Quando parar e recusar

Este fluxo cobre site institucional de um negócio físico. Recuse ou redirecione quando o pedido for tema WordPress, loja com carrinho, dashboard, app, SaaS ou painel admin. Diga o limite e ofereça só a vitrine estática.

Não invente CNPJ, endereço, horário, telefone ou foto do estabelecimento. Peça o dado ou deixe um placeholder explícito.

Não imprima, commite ou cole token, senha ou conteúdo de `.env` na conversa, no git ou no HTML.

## Pipeline

Siga nesta ordem. Não pule o brief. Não faça deploy antes do usuário confirmar o preview local.

1. Brief do negócio — copie `assets/PRODUCT.template.md` para `PRODUCT.md` e preencha. Leia `references/negocio-local-br.md`.
2. Captura do site atual — se houver URL, abra, leia o HTML visível, anote textos reais, fotos úteis, páginas e o que falha (lento, ilegível no celular, sem CTA, endereço errado). Guarde o "antes" em `ANTES.md`.
3. Direção visual — leia `references/design-floor.md`. Escreva em `DESIGN.md` uma paleta de 4 a 6 cores nomeadas, um ou dois tipos, o conceito de layout em uma frase e o elemento que carrega a personalidade. Revise o plano contra os defaults de IA listados no floor. Só então gere código.
4. Build estático — gere o site em `dist/` (HTML + CSS + JS mínimo + imagens). Mobile primeiro. Uma oferta. Um CTA principal.
5. Checklist de conversão — confira `references/negocio-local-br.md` antes de chamar pronto.
6. Preview — sirva `dist/` localmente e peça o ok do usuário:

   ```bash
   python -m http.server 8080 --directory dist
   ```

   Abra `http://localhost:8080`. Confira também na largura de 360px (DevTools,
   modo dispositivo) antes de mostrar — este site vive no celular.

7. Deploy — só com ok explícito. Leia `references/hostgator-cpanel.md`, rode
   primeiro com `--dry-run` e só então de verdade:

   ```bash
   python scripts/deploy-cpanel.py --dry-run
   python scripts/deploy-cpanel.py
   ```

## Brief mínimo

Sem estes campos o visual vira template. Complete antes de desenhar.

- nome do negócio, cidade, bairro
- o que vende, para quem, em uma frase
- oferta principal (o que a pessoa ganha ao chamar)
- WhatsApp com DDD
- endereço e horário
- tom (simples, acolhedor, técnico, popular, sofisticado)
- 1 a 3 fotos reais, se existirem
- URL do site feio, se existir

O brief vence o gosto da skill. Padaria não parece fintech. Oficina não parece spa.

## Build

Empilhe pouco. Hospedagem compartilhada não é lugar de React, Next ou bundler obrigatório.

- `dist/index.html` como entrada
- CSS próprio em arquivo separado, variáveis na raiz
- JS só para menu mobile, WhatsApp flutuante ou mapa
- imagens em `dist/img/`, comprimidas, com `alt` real
- `dist/.htaccess` com HTTPS e cache de estáticos, se o destino for Apache/cPanel
- fontes via Google Fonts ou arquivo local — nunca mais de duas famílias

Páginas típicas de um comércio local. Home, serviços, sobre, contato. Muitos negócios cabem em uma página com âncoras. Prefira uma página quando o conteúdo for curto.

HTML semântico. Um `h1`. CTA com texto de ação ("Chamar no WhatsApp"), não "Enviar". Links de telefone em `tel:` e WhatsApp em `https://wa.me/55DDDNUMERO` com mensagem pronta.

## Deploy

`scripts/deploy-cpanel.py` lê o `.env` e envia `dist/` para `public_html` (ou o caminho em `DEPLOY_PATH`). Só biblioteca padrão do Python — nada de instalar.

Antes de rodar.

- confirme que `.env` existe, está no `.gitignore` e não vai para o git — o script recusa rodar se o `.env` estiver versionado
- confirme domínio ou addon domain no plano
- avise que o conteúdo atual da pasta de destino será sobrescrito arquivo a arquivo, sem apagar o que o script não envia

O script confere sozinho, sem você pedir:

- se a pasta remota já tem `index.php` ou `default.php` — esses ganham do `index.html` novo e deixam a home velha no ar mesmo com o deploy dando certo
- se alguma imagem passa de 500 KB
- se o cPanel realmente aceitou cada arquivo, lendo o JSON de verdade
- **se o site publicado abriu e é a home nova**, comparando o `<title>` que subiu com o que a URL devolve

Ele nunca imprime o token, e o token não vai por linha de comando — só no header da requisição.

Se a verificação final falhar, o script sai com código 1 e diz o motivo. Não anuncie "site no ar" antes de ver o ✅.

Depois disso, abra o domínio no celular e confira WhatsApp e mapa.

## Qualidade em um ciclo

Construa inteiro. Inspecione uma vez no desktop e no mobile. Corrija tudo num lote. Pare. Loop aberto de "mais um polish" gasta token e piora o resultado.

Leia `references/design-floor.md` de novo só se o lote de correção exigir direção, não como ritual.
