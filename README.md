# g4os-habblaud

Mostra as sessões do **G4 OS** como personagens no escritório do [Habblaud](https://github.com/marmottajr/habblaud)
(https://habblaud.localhost) em qualquer computador.

O script `g4os` traduz a atividade do agente (sessão aberta, pedido recebido, ferramenta em uso, fim de
turno) em eventos para a API local do Habblaud (`POST /api/codex/events`). O personagem aparece com a letra
**G4**, na sala do projeto em uso.

## Requisitos

- Habblaud instalado e no ar (ver README do Habblaud) — em Docker ou não.
- macOS ou Linux (no Windows, dentro do WSL).
- Nenhuma dependência além de `curl` e `python3` (ambos já vêm no macOS/Ubuntu).

## Instalar

```bash
git clone https://github.com/pmaquin/g4os-habblaud.git
cd g4os-habblaud
./install.sh
```

O instalador:
1. Copia o `g4os` para `~/.local/bin` (e garante o PATH);
2. Cria a conta `~/.codex-g4` (é assim que o Habblaud detecta o personagem) e o alias `g4` no shell;
3. Instala a skill `g4os-habblaud` no workspace do G4 OS (se achar `~/.g4os/workspaces`);
4. Se o Habblaud já estiver rodando, recria o container para detectar a conta nova
   (`npm run docker:up` em `~/habblaud`, quando aplicável).

Depois, use normalmente: em qualquer sessão de trabalho do G4 OS, o agente aparece no escritório.

## Uso manual

```bash
g4os start "Nome do projeto"   # abre a sessão no escritório
g4os prompt "o que foi pedido" # marca "trabalhando"
g4os tool "lendo os logs"      # atividade em tempo real
g4os stop                      # fim do turno (ocioso)
g4os end                       # fecha a sessão
```

## Limitações (por enquanto)

- One-way: o escritório mostra o que o G4 OS faz; mensagens e aprovações clicadas lá não chegam ao agente.
- O personagem usa o selo CODEX (é o único protocolo de eventos aberto do Habblaud).

## Residentes: agentes fixos numa sala

O comando `residentes` (instalado junto) mantém agentes **fixos no escritório**, cada um na própria
sala, com papel e prompt próprios — e que trabalham de verdade: uma tarefa roda o Claude Code
(`claude -p`) e o escritório mostra o progresso em tempo real.

```bash
residentes start               # liga a presença de todos (daemon em background)
residentes run g4os "tarefa"   # dá uma tarefa a um residente
residentes status              # o que cada um está fazendo
residentes stop                # todos saem do escritório
```

Cadastre os residentes em `~/.habblaud/residentes.json`:

```json
{
  "habblaud": "http://127.0.0.1:4747",
  "conta": ".codex-g4",
  "residentes": [
    { "id": "g4os", "nome": "G4 OS", "sala": "Central G4",
      "papel": "Chef de staff do escritório",
      "prompt": "Você é o G4 OS, residente permanente do escritório.",
      "cwd": "~/projetos/jarvis", "memoria": true, "permissivo": true }
  ]
}
```

- `sala` — sala própria do residente (criada no escritório se não existir).
- `prompt`/`papel` — instrução de sistema do agente.
- `cwd` — diretório de trabalho real das tarefas.
- `memoria` — continua conversas anteriores do residente (`--continue`).
- `permissivo` — roda sem pedir aprovação (necessário em tarefas não interativas).

Requisito para executar tarefas: Claude Code autenticado (`claude auth login`).
