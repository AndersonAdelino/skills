---
name: local-site-lift
description: >-
  Refaz o site feio de um negócio local como página estática rápida, decidindo
  a direção visual antes de escrever código. Entrega brief, auditoria do site
  atual e a pasta dist/ pronta. Ativa em "melhora o site da padaria", "site
  feio de comércio", "refaz a vitrine da oficina", "landing page pro meu
  salão", "site de clínica/restaurante/pet shop/advogado/barbearia", "meu site
  é lento e feio", "quero um site simples com WhatsApp", "redesign a local
  business site". NÃO use para tema WordPress, loja com carrinho ou checkout,
  área logada, blog com CMS, dashboard, app, SaaS, painel admin, nem projeto
  Next/React que precise de servidor — diga o limite e ofereça só a vitrine
  estática. Esta skill NÃO publica: para subir no cPanel, o trabalho é da
  skill cpanel-deploy. Se o pedido for vago como "faz um site", pergunte que
  negócio é e se tem endereço físico antes de acionar.
argument-hint: "<nome do negócio + cidade> [URL do site atual]"
license: MIT
---

# Local Site Lift

Transforma site feio de negócio local em página estática rápida, com cara
própria, feita para converter no celular.

O trabalho termina numa pasta `dist/` pronta. **Publicar é de outra skill**, a
`cpanel-deploy` — aqui não há token, não há `.env`, não há hospedagem.

O trabalho não é "fazer um site bonito". É colocar o comércio no ar com um caminho óbvio até o WhatsApp.

## Quando parar e recusar

Este fluxo cobre site institucional de um negócio físico. Recuse ou redirecione quando o pedido for tema WordPress, loja com carrinho, dashboard, app, SaaS ou painel admin. Diga o limite e ofereça só a vitrine estática.

Não invente CNPJ, endereço, horário, telefone ou foto do estabelecimento. Peça o dado ou deixe um placeholder explícito.

Não imprima, commite ou cole token, senha ou conteúdo de `.env` na conversa, no git ou no HTML.

## Onde o trabalho mora

Uma pasta por cliente, **dentro da pasta em que a conversa está acontecendo**:

```
<pasta-do-projeto>/clientes/<nome-do-cliente>/
├── PRODUCT.md     brief
├── ANTES.md       auditoria do site atual
├── DESIGN.md      direção visual
├── dist/          o site
└── origem/        o que foi baixado do site antigo (rascunho)
```

Nunca jogue em `Downloads` nem em pasta temporária: some, e o cliente volta
daqui a três meses pedindo ajuste.

**Se a pasta do projeto for um repositório git, ponha `clientes/` no
`.gitignore` antes de criar o primeiro arquivo.** O `PRODUCT.md` carrega CNPJ,
telefone e endereço de um negócio real, e isso não entra num repositório
público.

## Pipeline

Siga nesta ordem. Não pule o brief, e não publique nada antes do usuário aprovar o preview local.

1. Brief do negócio — copie `assets/PRODUCT.template.md` para `PRODUCT.md` e preencha. Leia `references/negocio-local-br.md`.
2. Captura do site atual — se houver URL, abra, leia o HTML visível, anote textos reais, fotos úteis, páginas e o que falha (lento, ilegível no celular, sem CTA, endereço errado). Guarde o "antes" em `ANTES.md`.
3. Perfil do Google — se houver `APIFY_TOKEN`, consulte. É a **única fonte
   acessível de foto real do lugar**, e o perfil é mantido pelo dono, então
   costuma estar mais certo que o site.

   ```bash
   python scripts/negocio.py consultar "<nome> <cidade>" --out google.json
   python scripts/negocio.py fotos google.json --out origem/google --n 4
   ```

   **Confronte com o `PRODUCT.md` e mostre as divergências ao usuário.** No
   primeiro site real o Google trazia `231` onde o site dizia `23`, e marcava
   sábado como fechado enquanto o site anunciava 7h30 às 12h. Endereço errado
   manda gente para o lugar errado: divergência é assunto do dono, não escolha
   sua.

   **Nota abaixo de 4,0 não vira selo no site**, e `aggregateRating` só entra
   no schema com o número verificado. Leia as avaliações de uma estrela e conte
   ao dono o que elas repetem: costuma ser problema de operação que o site não
   conserta e não deve esconder.

   **Olhe as fotos antes de usar.** São mistura de foto do dono e de cliente, e
   podem ter rosto de funcionário, que exige consentimento. Toda foto daí é
   candidata marcada no `PRODUCT.md`, nunca publicação direta.

   Sem o token, pule: o site sai igual, só sem foto real e sem nota.

4. Direção visual — leia `references/design-floor.md`. Escreva em `DESIGN.md` uma paleta de 4 a 6 cores nomeadas, um ou dois tipos, o conceito de layout em uma frase e o elemento que carrega a personalidade. Revise o plano contra os defaults de IA listados no floor. Só então gere código.
5. Imagens — leia a seção "Imagem" do `design-floor.md`. **A decisão é sua, o
   `scripts/imagens.py` só executa.** Primeiro: a imagem afirma algo sobre o
   negócio (fachada, sala, equipe)? Então só foto real deles, ou nenhuma. Se
   não: busque no Pexels quando for assunto comum do mundo real, e gere na
   kie.ai quando for específico da ideia deste site.

   ```bash
   python scripts/imagens.py buscar "<termo em ingles>" --n 5 --previa /tmp/p
   python scripts/imagens.py pegar <id> --out dist/img/hero
   python scripts/imagens.py gerar "<prompt>" --out dist/img/x   # custa crédito
   ```

   **Antes de `gerar`, mostre o prompt e espere o ok:** custa crédito.

6. Build estático — gere o site em `dist/` (HTML + CSS + JS mínimo + imagens). Mobile primeiro. Uma oferta. Um CTA principal.
7. Aferir o artesanato — **antes de mostrar qualquer coisa ao usuário**:

   ```bash
   python scripts/aferir.py dist/
   ```

   Ele mede o que separa site de agência de site amador: tamanho do `h1`,
   contraste da escala, estados de interação, grade no desktop, rodapé. Sai com
   código 1 e diz o número de cada falha. **Corrija tudo antes do preview.**

   Isso existe porque duas entregas saíram planas e com metade da tela vazia,
   seguindo um `design-floor.md` que só listava proibições.

8. Checklist de conversão — confira `references/negocio-local-br.md` antes de chamar pronto.
9. Preview — sirva `dist/` localmente e peça o ok do usuário:

   ```bash
   python -m http.server 8080 --directory dist
   ```

   Abra `http://localhost:8080`. Confira também na largura de 360px (DevTools,
   modo dispositivo) antes de mostrar — este site vive no celular.

10. Publicar — só com ok explícito, e é outra skill. Peça a **cpanel-deploy**,
   que sobe a pasta `dist/` num cPanel e confere se o endereço no ar é mesmo a
   página nova. Se o usuário hospeda em outro lugar (Vercel, Netlify), o
   `dist/` é estático puro e serve igual.

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

- **leia o chão numérico do `design-floor.md` antes de escrever CSS.** `h1` de
  3,5rem, no máximo 8 tamanhos de fonte, grade de verdade no desktop
- `dist/index.html` como entrada
- CSS próprio em arquivo separado, variáveis na raiz
- JS só para menu mobile, WhatsApp flutuante ou mapa
- imagens em `dist/img/`, comprimidas, com `alt` real
- `dist/.htaccess` com HTTPS e cache de estáticos, se o destino for Apache (modelo em `assets/htaccess.template`). É ele que faz o CDN cachear
- fontes via Google Fonts ou arquivo local — nunca mais de duas famílias

Páginas típicas de um comércio local. Home, serviços, sobre, contato. Muitos negócios cabem em uma página com âncoras. Prefira uma página quando o conteúdo for curto.

HTML semântico. Um `h1`. CTA com texto de ação ("Chamar no WhatsApp"), não "Enviar". Links de telefone em `tel:` e WhatsApp em `https://wa.me/55DDDNUMERO` com mensagem pronta.

## Publicar

Não é trabalho desta skill. O `dist/` é HTML, CSS, JS e imagem: sobe em
qualquer lugar que sirva arquivo estático.

Para cPanel (HostGator e equivalentes), use a skill **cpanel-deploy**: ela lê o
token de um `.env`, não apaga nada no servidor, avisa se houver `index.php`
velho ganhando da home nova, e confere no fim se a URL publicada é a página que
subiu.

Antes de entregar, avise o cliente sobre o que ficou marcado como
**[CONFIRMAR]** no `PRODUCT.md`. Em site de saúde, alimentação ou serviço
regulado, isso costuma incluir responsável técnico e registro profissional.

## Qualidade em um ciclo

Construa inteiro. Inspecione uma vez no desktop e no mobile. Corrija tudo num lote. Pare. Loop aberto de "mais um polish" gasta token e piora o resultado.

Leia `references/design-floor.md` de novo só se o lote de correção exigir direção, não como ritual.
