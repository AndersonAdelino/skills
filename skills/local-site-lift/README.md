# local-site-lift

Pega o site feio de um comércio local e reconstrói como página estática rápida,
decidindo a direção visual **antes** de escrever código.

O trabalho não é "fazer um site bonito". É colocar o comércio no ar com um
caminho óbvio até o WhatsApp.

```
Melhora o site da Padaria São José em Currais Novos/RN.
WhatsApp 84 99999-1234, abre 6h-19h, fecha domingo, Rua Grande 120, Centro.
```

## O que sai

```
clientes/padaria-sao-jose/
├── PRODUCT.md     o brief, com o que precisa ser confirmado pelo dono
├── ANTES.md       a auditoria do site atual, com números medidos
├── DESIGN.md      paleta, tipos, layout, e a checagem contra os defaults de IA
├── dist/          o site: HTML + CSS + JS mínimo + imagens
└── origem/        o que foi baixado do site antigo
```

**Termina aqui.** Publicar é da skill [cpanel-deploy](../cpanel-deploy/) — o
`dist/` é estático puro e sobe em qualquer lugar que sirva arquivo.

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

**Python 3** (só para servir o preview) e um navegador. Nada de `pip install`,
nada de conta em lugar nenhum, nenhum token.

O site que ela gera não precisa de build: é HTML, CSS e um pouco de JS. Nada de
React, Next ou bundler — hospedagem compartilhada não é lugar disso.

## Como ela decide o visual

Primeiro o `DESIGN.md`, depois o código. A direção sai do negócio real, não do
gosto da skill: *padaria não parece fintech, oficina não parece spa*.

`references/design-floor.md` tem a lista de **defaults que denunciam site
gerado** — creme quente com serif e terracota, fundo preto com um neon, cards
idênticos com a mesma sombra, eyebrow em caixa alta, seta `→` em todo botão,
Inter como personalidade, glassmorphism. O plano é revisado contra essa lista
antes de virar HTML.

## O que ela não inventa

- CNPJ, endereço, horário, telefone: pede ou deixa placeholder explícito
- avaliação, selo, "mais de X clientes": só com fonte
- **foto**: a ordem é foto real do negócio → Pexels → IA, e **IA só para
  ilustração**. Nada de recepção, fachada, sala ou equipe gerados, que afirmam
  como é o lugar sem ser
- depoimento: só real, com nome e data, do perfil público do Google

E lê as avaliações **ruins** também, para contar ao dono. Costumam apontar um
problema de operação que o site não conserta e não deve esconder.

## O que entra e o que não entra

**Entra:** vitrine de padaria, oficina, clínica, salão, restaurante,
profissional liberal. WhatsApp, mapa, horário, schema `LocalBusiness`.

**Não entra:** tema WordPress, WooCommerce, carrinho, checkout, área logada,
blog com CMS, dashboard, app. Isso é outro produto — a skill diz o limite e
oferece só a vitrine.

## Limites conhecidos

- **O brief assume um endereço.** Negócio com várias unidades funciona, mas o
  template não tem lugar para isso ainda
- **Não gera conteúdo do negócio.** Foto, CNPJ, horário e depoimento vêm de você
- **Não publica.** Ver [cpanel-deploy](../cpanel-deploy/)

## Licença

MIT.
