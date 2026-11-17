---
name: "Habblaud: Presença do G4 OS (REGRA 0)"
description: "REGRA 0, sempre ativa: anunciar esta sessão no escritório do Habblaud (comando g4os) em TODO turno com trabalho real — arquivos, comandos, navegação, bancos. Usar sem @menção e sem exceção; falha do g4os nunca bloqueia o trabalho."
---

# Habblaud: presença do G4 OS no escritório

O comando `g4os` (`~/.g4os/workspaces/jarvis/habblaud-g4os/g4os`, no PATH) mostra esta sessão do G4 OS como um
personagem no escritório do Habblaud (https://habblaud.localhost). Use em TODO turno de trabalho real
(quando você for executar ferramentas de verdade — arquivos, comandos, pesquisas). Pule em conversas curtas
sem ferramentas.

## Protocolo por turno

1. **Início do turno**, antes da primeira ferramenta:
   - `g4os start "<projeto>"` — só se ainda não há sessão (o comando emite a sessão nova).
     Projeto = nome curto do que está sendo feito (ex.: "Site do cliente", "Manutenção Habblaud").
   - `g4os prompt "<o que o usuário pediu, em ~1 frase>"`.
2. **Durante o trabalho**: antes de cada bloco de ferramentas, `g4os tool "<o que vai fazer agora>"`.
   Prefira verbos: "lendo logs do Docker", "editando index.html", "consultando o Databricks".
3. **Fim do turno** (antes de responder ao usuário): `g4os stop` — o personagem fica ocioso.
   Se a sessão encerrou de vez, `g4os end` o remove.

O estado da sessão fica em `$TMPDIR/g4os-habblaud-session`. Se `g4os tool` reclamar de sessão ausente,
rode `g4os start` de novo. Não trate falha do `g4os` como erro do turno: o Habblaud pode estar desligado;
siga o trabalho normalmente.
