#!/usr/bin/env bash
# Instalador do g4os-habblaud: script no PATH, conta ~/.codex-g4, skill no workspace do G4 OS.
set -euo pipefail
cd "$(dirname "$0")"
HOME_DIR="${HOME:?}"

echo "==> 1/4. Script no PATH"
mkdir -p "$HOME_DIR/.local/bin"
install -m 0755 g4os "$HOME_DIR/.local/bin/g4os"
case ":$PATH:" in
  *":$HOME_DIR/.local/bin:"*) ;;
  *) for RC in ~/.zshrc ~/.bashrc; do
       [ -f "$RC" ] && ! grep -q '.local/bin' "$RC" && printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$RC"
     done ;;
esac
G4OS="$HOME_DIR/.local/bin/g4os"

echo "==> 2/4. Conta ~/.codex-g4 (personagem G4 no Habblaud)"
mkdir -p "$HOME_DIR/.codex-g4/thread-writer-locks"
touch "$HOME_DIR/.codex-g4/config.toml"
if ! grep -q "codex-g4" ~/.zshrc 2>/dev/null; then
  printf "\nalias g4='CODEX_HOME=%s/.codex-g4 codex'\n" "$HOME_DIR" >> ~/.zshrc
fi

echo "==> 3/4. Skill no workspace do G4 OS"
for WS in "$HOME_DIR"/.g4os/workspaces/*/; do
  [ -d "$WS" ] || continue
  mkdir -p "${WS}skills/g4os-habblaud"
  cp -r skill-g4os-habblaud/. "${WS}skills/g4os-habblaud/"
  echo "    skill instalada em ${WS}skills/g4os-habblaud"
done

echo "==> 4/4. Habblaud"
if curl -s --max-time 2 http://127.0.0.1:4747/api/health >/dev/null 2>&1; then
  if [ -d "$HOME_DIR/habblaud" ]; then
    echo "    recriando o container para detectar a conta nova…"
    (cd "$HOME_DIR/habblaud" && npm run docker:up >/dev/null 2>&1 || echo "    aviso: rode 'npm run docker:up' em ~/habblaud para detectar a conta")
  fi
else
  echo "    Habblaud não está no ar; suba-o depois ('npm run docker:up' em ~/habblaud) que a conta é detectada."
fi

echo
echo "Pronto. Teste:  $G4OS start 'Teste' && $G4OS stop"
