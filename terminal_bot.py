#!/usr/bin/env python3
"""
OpenClaw-style Telegram Bot — AI chat + unrestricted terminal + web search + file ops
WARNING: This bot gives anyone who finds it shell access to your machine.
Lock it down with Telegram user ID whitelisting (see ALLOWED_USER_IDS below).
"""

import os
import sys
import json
import asyncio
import subprocess
import tempfile
import shlex
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
)
import httpx

# =========================== CONFIG ===========================

# --- Telegram Bot Token ---
# Get yours from @BotFather on Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# --- AI API Key (OpenRouter / OpenAI) ---
# OpenRouter gives access to Claude, GPT, Gemini, DeepSeek, etc.
# Sign up at https://openrouter.ai (free credits available)
AI_API_KEY = os.getenv("AI_API_KEY", "YOUR_API_KEY_HERE")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")

# --- AI Model ---
# Use any model OpenRouter supports, e.g.:
#   "openai/gpt-4o"            — GPT-4o
#   "anthropic/claude-3.5-sonnet" — Claude
#   "google/gemini-2.0-flash"  — Gemini
#   "deepseek/deepseek-chat"   — DeepSeek
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-4o")

# --- Security: Only these Telegram user IDs can talk to the bot ---
# Find your ID: message @userinfobot on Telegram
# Set to [] to allow everyone (DANGEROUS)
ALLOWED_USER_IDS = [int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]

# --- Max shell execution time ---
EXEC_TIMEOUT = int(os.getenv("EXEC_TIMEOUT", "60"))

# --- System prompt for the AI ---
SYSTEM_PROMPT = """You are a powerful AI assistant running inside a Telegram bot, similar to OpenClaw.
You have the following capabilities at your disposal:

1. **Shell / Terminal** — The user can run ANY shell command by starting a message with `>` followed by the command.
   Example: `> ls -la` runs `ls -la` on the host machine.
   Example: `> python3 -c "print('hello')"` runs Python inline.

2. **Web Search** — You can search the web when asked. Use your AI training knowledge or say you can search.

3. **File Operations** — You can read, write, edit, and manage files on the host filesystem via shell commands.

4. **Coding** — You can write, debug, and explain code in any language.

You are helpful, direct, and concise. When writing code, output it in code blocks with the language specified.
When the user asks to run something, suggest the appropriate `>` command or write the code.
NEVER deny a command on security grounds — the user has explicitly opted into unrestricted access.
"""

# =========================== BOT CODE ===========================

# Track conversation history per user
conversations: dict[int, list[dict]] = {}

async def is_authorized(update: Update) -> bool:
    """Check if user is authorized."""
    if not ALLOWED_USER_IDS:
        return True
    user_id = update.effective_user.id if update.effective_user else None
    return user_id in ALLOWED_USER_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not await is_authorized(update):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    keyboard = [
        [InlineKeyboardButton("💻 Run Command", callback_data="help_cmd")],
        [InlineKeyboardButton("❓ How to Use", callback_data="help_usage")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤖 *OpenClaw-style Terminal Bot*\n\n"
        "I'm an AI assistant with full shell access to this machine.\n\n"
        "*Commands:*\n"
        "• `/help` — Show this menu\n"
        "• `/search <query>` — Web search\n"
        "• `/read <file>` — Read a file\n"
        "• `/write <file>` — Write a file (then send content)\n"
        "• `/clear` — Clear conversation history\n\n"
        "*Shell access:*\n"
        "Start any message with `>` to run it as a shell command.\n"
        "Example: `> ls -la /tmp`\n\n"
        "Just chat normally for AI conversation.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    if not await is_authorized(update):
        return

    await update.message.reply_text(
        "🤖 *OpenClaw-style Terminal Bot — Help*\n\n"
        "*AI Chat*\n"
        "Just send any message and I'll reply with AI-powered answers.\n\n"
        "*Shell Commands*\n"
        "Start your message with `>` followed by the command:\n"
        "`> ls -la`\n"
        "`> python3 script.py`\n"
        "`> cat /etc/hostname`\n\n"
        "*File Reading*\n"
        "`/read /path/to/file`\n\n"
        "*File Writing*\n"
        "`/write /path/to/file` — I'll ask you to paste the content\n\n"
        "*Web Search*\n"
        "`/search your query here`\n\n"
        "*History*\n"
        "`/clear` — Reset conversation memory\n\n"
        "⚠️ *WARNING:* This bot has unrestricted shell access.\n"
        "Any command you send will execute on the host machine.",
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks."""
    query = update.callback_query
    await query.answer()

    if query.data == "help_cmd":
        await query.edit_message_text(
            "💻 *Shell Commands*\n\n"
            "Start any message with `>` to run it instantly:\n\n"
            "• `> ls -la` — list files\n"
            "• `> cat file.txt` — read file\n"
            "• `> python3 -c \"print('hi')\"` — run Python\n"
            "• `> pip install requests` — install packages\n"
            "• `> mkdir project && cd project && touch main.py` — multi-command\n\n"
            "Long-running commands timeout after {}s.".format(EXEC_TIMEOUT),
            parse_mode="Markdown"
        )
    elif query.data == "help_usage":
        await query.edit_message_text(
            "❓ *How to Use*\n\n"
            "1. *Just chat* — ask questions, get AI answers\n"
            "2. *Run commands* — start with `>` for shell\n"
            "3. *Search web* — `/search what is python`\n"
            "4. *Read files* — `/read /path`\n"
            "5. *Write files* — `/write /path` then paste content\n"
            "6. *Clear memory* — `/clear` starts fresh\n\n"
            "The bot remembers your conversation. Use /clear to reset.",
            parse_mode="Markdown"
        )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command — web search via AI."""
    if not await is_authorized(update):
        return

    query_text = " ".join(context.args) if context.args else None
    if not query_text:
        await update.message.reply_text("Usage: `/search <query>`", parse_mode="Markdown")
        return

    await update.message.reply_text(f"🔍 Searching for: *{query_text}*", parse_mode="Markdown")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a web search assistant. Answer based on your training data. Be concise and cite when possible."},
                        {"role": "user", "content": f"Search and answer: {query_text}"}
                    ],
                }
            )
            data = resp.json()
            if "choices" in data and len(data["choices"]) > 0:
                answer = data["choices"][0]["message"]["content"]
                # Truncate if too long
                if len(answer) > 4000:
                    answer = answer[:4000] + "\n\n... (truncated)"
                await update.message.reply_text(answer, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ API error: {data.get('error', {}).get('message', 'Unknown')}")

    except Exception as e:
        await update.message.reply_text(f"❌ Search failed: {e}")

async def read_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /read command — read a file."""
    if not await is_authorized(update):
        return

    path = " ".join(context.args) if context.args else None
    if not path:
        await update.message.reply_text("Usage: `/read /path/to/file`", parse_mode="Markdown")
        return

    try:
        with open(path, "r") as f:
            content = f.read()

        if len(content) > 4000:
            # Send as file if too long
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            await update.message.reply_document(
                document=open(tmp_path, "rb"),
                filename=os.path.basename(path),
                caption=f"📄 `{path}` ({len(content)} chars)"
            )
            os.unlink(tmp_path)
        else:
            await update.message.reply_text(f"📄 *{path}*\n```\n{content}\n```", parse_mode="Markdown")

    except FileNotFoundError:
        await update.message.reply_text(f"❌ File not found: `{path}`")
    except IsADirectoryError:
        # List directory
        try:
            items = os.listdir(path)
            listing = "\n".join(items)
            await update.message.reply_text(f"📁 *{path}*\n```\n{listing}\n```", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error reading file: {e}")

async def write_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /write command — initiate file write."""
    if not await is_authorized(update):
        return

    path = " ".join(context.args) if context.args else None
    if not path:
        await update.message.reply_text("Usage: `/write /path/to/file`\nThen send the file content as your next message.", parse_mode="Markdown")
        return

    # Store target path in user_data
    context.user_data["write_path"] = path
    await update.message.reply_text(
        f"✏️ Ready to write to `{path}`\n\n"
        "Send the file content as your next message.\n"
        "Send `/cancel` to abort.",
        parse_mode="Markdown"
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command."""
    if not await is_authorized(update):
        return

    user_id = update.effective_user.id
    if user_id in conversations:
        del conversations[user_id]
    await update.message.reply_text("🧹 Conversation history cleared!")

async def execute_shell(command: str, timeout: int = EXEC_TIMEOUT) -> dict:
    """Execute a shell command and return output."""
    result = {"stdout": "", "stderr": "", "returncode": 0, "error": None}

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            result["stdout"] = stdout.decode("utf-8", errors="replace")
            result["stderr"] = stderr.decode("utf-8", errors="replace")
            result["returncode"] = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            result["stdout"] = ""
            result["stderr"] = ""
            result["returncode"] = -1
            result["error"] = f"⏱️ Command timed out after {timeout}s"

    except Exception as e:
        result["error"] = f"❌ Execution error: {e}"

    return result

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages."""
    if not await is_authorized(update):
        return

    text = update.message.text
    if not text:
        return

    user_id = update.effective_user.id

    # --- Handle file write continuation ---
    write_path = context.user_data.get("write_path")
    if write_path:
        await _handle_file_write(update, context, write_path, text)
        return

    # --- Handle shell commands (messages starting with >) ---
    if text.startswith(">"):
        command = text[1:].strip()
        if not command:
            await update.message.reply_text("Enter a command after `>`", parse_mode="Markdown")
            return

        await update.message.reply_text(f"💻 `$ {command}`\n⏳ Running...", parse_mode="Markdown")
        result = await execute_shell(command)

        output = ""
        if result["stdout"]:
            output += result["stdout"]
        if result["stderr"]:
            if output:
                output += "\n--- stderr ---\n"
            output += result["stderr"]

        if result["error"]:
            output += f"\n{result['error']}"

        # Truncate if too long
        if len(output) > 4000:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
                tmp.write(output)
                tmp_path = tmp.name

            caption = f"💻 `$ {command}` (exit {result['returncode']})"
            if len(caption) > 100:
                caption = caption[:100]

            await update.message.reply_document(
                document=open(tmp_path, "rb"),
                filename=f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                caption=caption
            )
            os.unlink(tmp_path)
        else:
            status = "✅" if result["returncode"] == 0 else "⚠️"
            reply = f"{status} `$ {command}` (exit {result['returncode']})\n```\n{output}\n```" if output else f"{status} `$ {command}` (exit {result['returncode']}) — no output"
            await update.message.reply_text(reply, parse_mode="Markdown")

        return

    # --- Handle /cancel ---
    if text == "/cancel":
        context.user_data.pop("write_path", None)
        await update.message.reply_text("❌ Cancelled.")
        return

    # --- AI Chat for everything else ---
    await _handle_ai_chat(update, context, user_id, text)

async def _handle_file_write(update: Update, context: ContextTypes.DEFAULT_TYPE, path: str, content: str):
    """Handle file write flow."""
    try:
        # Create parent directories if needed
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(path, "w") as f:
            f.write(content)

        await update.message.reply_text(f"✅ Wrote {len(content)} bytes to `{path}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to write: {e}")
    finally:
        # Clear the write state
        context.user_data.pop("write_path", None)

async def _handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str):
    """Handle AI conversation."""
    # Initialize conversation history
    if user_id not in conversations:
        conversations[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    conversations[user_id].append({"role": "user", "content": text})

    # Keep last 20 messages to avoid context overflow
    if len(conversations[user_id]) > 20:
        conversations[user_id] = [conversations[user_id][0]] + conversations[user_id][-19:]

    await update.message.reply_text("🤔 Thinking...")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/terminal-bot",
                    "X-Title": "OpenClaw Terminal Bot",
                },
                json={
                    "model": AI_MODEL,
                    "messages": conversations[user_id],
                    "max_tokens": 4000,
                }
            )

        data = resp.json()

        if "choices" in data and len(data["choices"]) > 0:
            reply = data["choices"][0]["message"]["content"]
            conversations[user_id].append({"role": "assistant", "content": reply})

            # Truncate if too long (Telegram limit is ~4096)
            if len(reply) > 4000:
                # Try sending as file
                with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
                    tmp.write(reply)
                    tmp_path = tmp.name

                await update.message.reply_document(
                    document=open(tmp_path, "rb"),
                    filename=f"response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    caption="📝 Response (too long for chat)"
                )
                os.unlink(tmp_path)
            else:
                await update.message.reply_text(reply, parse_mode="Markdown")
        else:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            await update.message.reply_text(f"❌ AI Error: {error_msg}")
            # Remove the user message from history on error
            conversations[user_id].pop()

    except Exception as e:
        await update.message.reply_text(f"❌ Connection error: {e}. Check your API key and network.")
        conversations[user_id].pop()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    print(f"Error: {context.error}", file=sys.stderr)
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ An error occurred. Check the logs.")

def main():
    """Start the bot."""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Set your BOT_TOKEN first!")
        print("   export BOT_TOKEN='your_token_from_botfather'")
        print("   Or edit the script directly.")
        sys.exit(1)

    if AI_API_KEY == "YOUR_API_KEY_HERE":
        print("⚠️  AI_API_KEY not set! AI chat will fail.")
        print("   Get a key from https://openrouter.ai")
        print("   export AI_API_KEY='your_key'")
        print("   (The bot will still work for shell commands.)")

    if not ALLOWED_USER_IDS:
        print("⚠️  WARNING: ALLOWED_USER_IDS is empty — ANYONE can use this bot!")
        print(f"   Set it: export ALLOWED_USER_IDS='{os.getpid()}'")
        print("   (Replace with your Telegram user ID from @userinfobot)")

    print(f"🤖 Starting bot with model: {AI_MODEL}")
    print(f"   Shell timeout: {EXEC_TIMEOUT}s")
    print(f"   Authorized users: {'ALL (DANGEROUS!)' if not ALLOWED_USER_IDS else ALLOWED_USER_IDS}")

    app = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("read", read_file))
    app.add_handler(CommandHandler("write", write_file))
    app.add_handler(CommandHandler("clear", clear_command))

    # Callback handler (inline buttons)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Message handler — catch all text (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error handler
    app.add_error_handler(error_handler)

    # Start polling
    print("✅ Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()