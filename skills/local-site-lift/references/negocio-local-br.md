# Negócio local no Brasil

Checklist e padrões que um site de comércio físico precisa para funcionar de verdade. Leia no brief e de novo antes de chamar o site de pronto.

## CTA principal

Um caminho principal. No Brasil esse caminho quase sempre é WhatsApp.

- link `https://wa.me/55DDDNUMERO?text=` com mensagem curta já preenchida
- número só dígitos depois do 55, sem zero à esquerda no DDD
- botão visível no hero e repetido no fim da página
- botão flutuante no mobile, sem tapar o conteúdo
- `tel:` só como apoio, não no lugar do WhatsApp

Não use gerador de link com tracking opaco. Não abra o app num `target` que quebra no iPhone.

## Dados que geram confiança

Coloque na home, visíveis, sem esconder no rodapé:

- nome do negócio
- cidade e bairro
- endereço completo, se o cliente for até lá
- horário de funcionamento, com dia fechado explícito
- WhatsApp
- se o usuário fornecer — CNPJ no rodapé, Instagram, Google Maps

Não invente avaliação, "mais de 10 mil clientes" ou selo que o negócio não tem. Depoimento só com nome e autorização. Sem foto de banco de imagem fingindo ser o salão.

## Mapa e presença local

Se houver endereço, embutir Google Maps (iframe oficial) ou link "Como chegar" para o app de mapas. Título da seção é o bairro, não "Localização".

Schema JSON-LD `LocalBusiness` (ou subtipo — `Bakery`, `AutoRepair`, `Dentist`) com nome, telefone, endereço e horário. Ajuda busca local. Não marque `AggregateRating` sem dado real.

## Página que cabe no bolso

Tráfego local é mobile. A home responde, nesta ordem:

1. quem é e o que resolve, na primeira tela
2. botão de WhatsApp
3. serviços em linguagem de cliente ("alinhamento e balanceamento", não "soluções automotivas")
4. prova curta (foto real, anos no bairro, um depoimento verdadeiro)
5. endereço, horário, mapa
6. de novo o WhatsApp

Evite carrossel automático, popup de newsletter, cookie banner teatro (o site estático típico desta skill não coleta dado). Se houver formulário, diga para que serve e para onde vai. Preferir WhatsApp a formulário.

## Conteúdo que não pode faltar por rubrica

Adapte. Não force seção vazia.

- alimentação — cardápio ou destaques do dia, retirada/entrega, alergia só se o negócio informar
- saúde/estética — o que atende, como marcar, se aceita convênio só com dado real
- oficina / assistência — tipos de serviço, marcas se fizer sentido, prazo só se for compromisso
- serviço profissional (advogado, contador) — áreas, cidade de atuação, CTA de conversa, sem juridiquês no hero

## Acessório técnico local

- idioma `pt-BR` no `html`
- título e description com cidade ("Padaria X em Bairro, Cidade")
- favicon simples
- Open Graph básico para o link no WhatsApp não ir vazio
- `preconnect` só do que a página usa (fonte, mapa)

## O que não entra

Carrinho, PIX checkout, área logada, blog com CMS, pop-up de "ganhe 10%". Isso é outro produto. A vitrine manda a pessoa falar com o negócio.
