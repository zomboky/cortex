from __future__ import annotations

import json
import shutil
import subprocess
import time

from .base import LLMProvider

MAX_RETRIES = 4
RETRY_DELAY_SECONDS = 5


class ClaudeCLIProvider(LLMProvider):
    """Backend LLM qui delegue chaque appel a la CLI Claude Code locale (`claude -p`),
    authentifiee via l'abonnement Claude connecte (OAuth) plutot qu'une cle API facturee
    a l'usage. Necessite `claude` dans le PATH et une session deja authentifiee."""

    def __init__(self, model: str) -> None:
        self.model = model
        self._cli = shutil.which("claude")
        if not self._cli:
            raise FileNotFoundError(
                "Executable 'claude' introuvable dans le PATH. Installe Claude Code et "
                "connecte-toi (`claude auth login`) pour utiliser le provider claude-cli."
            )

    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 4096) -> str:
        # Le prompt est passe via stdin (pas en argument CLI) : sur Windows, CreateProcess
        # rejette une ligne de commande trop longue (WinError 206) des que le contenu source
        # depasse quelques milliers de caracteres.
        cmd = [
            self._cli, "-p",
            "--model", self.model,
            "--output-format", "json",
            "--tools", "",
            "--disable-slash-commands",
            "--no-session-persistence",
        ]
        if system:
            cmd += ["--system-prompt", system]

        last_error = ""
        delay = RETRY_DELAY_SECONDS
        for attempt in range(1, MAX_RETRIES + 1):
            result = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    last_error = f"sortie non-JSON : {result.stdout[:500]!r}"
                else:
                    if not data.get("is_error"):
                        return data.get("result", "")
                    last_error = f"is_error=true : {data.get('result', '')[:500]}"
            else:
                last_error = (
                    f"code {result.returncode}, stderr={result.stderr.strip()[:500]!r}, "
                    f"stdout={result.stdout.strip()[:500]!r}"
                )
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
        raise RuntimeError(f"claude CLI a echoue apres {MAX_RETRIES} tentatives : {last_error}")
