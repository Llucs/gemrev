"""
Exemplo prático de uso da biblioteca GemRev em Python.

Uso:
  python3 example.py --cookie "SEU_COOKIE" [--proxy "http://host:port"] [--verbose]

Modo convidado (sem cookie - limitado a Flash, sem upload/histórico):
  python3 example.py --guest
"""

import asyncio
import sys
import argparse

from gemrev import Gemini, Model


async def demo_guest_mode():
    print("=" * 60)
    print("DEMO: Modo Convidado (Guest Mode)")
    print("=" * 60)

    client = Gemini(verbose=True)
    chat = client.new_chat()

    print("\n1. Enviando mensagem simples...")
    try:
        response = await chat.generate_content(prompt="Olá! Me diga seu nome em português.")
        print(f"   Resposta: {response.text[:200]}")
    except Exception as e:
        print(f"   Erro (esperado sem rede): {e}")

    print("\n2. Conversa de múltiplos turnos...")
    try:
        r1 = await chat.generate_content(prompt="Meu nome é João.")
        print(f"   Turno 1: {r1.text[:100]}")

        r2 = await chat.generate_content(prompt="Qual é o meu nome?")
        print(f"   Turno 2: {r2.text[:100]}")
    except Exception as e:
        print(f"   Erro: {e}")


async def demo_auth_mode(cookie, proxy=None, verbose=False):
    print("=" * 60)
    print("DEMO: Modo Autenticado")
    print("=" * 60)

    client = Gemini(secure_1psid=cookie, proxy=proxy, verbose=verbose)

    print("\n1. Inicializando cliente...")
    try:
        await client.init()
        print("   ✓ Cliente inicializado com sucesso")
    except Exception as e:
        print(f"   ✗ Falha na inicialização: {e}")
        return

    print("\n2. Listando modelos disponíveis...")
    try:
        models = await client.models()
        for m in models:
            print(f"   • {m.model_name} ({m.display_name}) {'[Advanced]' if m.advanced_only else ''}")
    except Exception as e:
        print(f"   Erro ao listar modelos: {e}")

    print("\n3. Enviando mensagem (modelo Flash)...")
    chat = client.new_chat(model=Model.BASIC_FLASH)
    try:
        response = await chat.generate_content(
            prompt="Explique Python async/await em 3 linhas."
        )
        print(f"   Resposta: {response.text[:300]}")
        print(f"   Modelo usado: {response.model}")
        print(f"   Conversation ID: {response.cid}")
        print(f"   Response ID: {response.rid}")
    except Exception as e:
        print(f"   Erro: {e}")

    print("\n4. Conversa multi-turno...")
    try:
        r1 = await chat.generate_content(prompt="Guarde este número: 42.")
        print(f"   Turno 1: {r1.text[:100]}")

        r2 = await chat.generate_content(prompt="Qual número eu pedi para guardar?")
        print(f"   Turno 2: {r2.text[:100]}")
    except Exception as e:
        print(f"   Erro: {e}")

    print("\n5. Testando streaming...")
    chat2 = client.new_chat(model=Model.BASIC_FLASH)
    try:
        print("   Resposta (streaming):", end=" ", flush=True)
        async for chunk in chat2.generate_content_stream(
            prompt="Escreva uma lista de 3 linguagens de programação."
        ):
            if chunk.text_delta:
                print(chunk.text_delta, end="", flush=True)
        print()
    except Exception as e:
        print(f"\n   Erro: {e}")

    print("\n6. Listando conversas recentes...")
    try:
        chats = await client.chats()
        print(f"   Total de conversas: {len(chats)}")
        for c in chats[:5]:
            print(f"   • {c.get('title', 'Sem título')} (cid: {c.get('cid', 'N/A')})")
    except Exception as e:
        print(f"   Erro: {e}")

    print("\n7. Listando Gems disponíveis...")
    try:
        gems = await client.gems()
        print(f"   Total de Gems: {len(gems)}")
        for g in gems[:5]:
            print(f"   • {g['name']} {'[Predefinido]' if g['predefined'] else '[Custom]'}")
    except Exception as e:
        print(f"   Erro: {e}")

    print("\n8. Testando Extended Thinking...")
    chat3 = client.new_chat(model=Model.BASIC_FLASH)
    try:
        response = await chat3.generate_content(
            prompt="Resolva: 17 × 23 = ?",
            extended_thinking=True,
        )
        if response.thoughts:
            print(f"   Raciocínio: {response.thoughts[:200]}...")
        print(f"   Resposta: {response.text[:200]}")
    except Exception as e:
        print(f"   Erro: {e}")

    print("\n9. One-shot prompt (client.ask)...")
    try:
        response = await client.ask(
            "Qual a capital do Brasil?",
            model=Model.BASIC_FLASH,
            temporary=True,
        )
        print(f"   Resposta: {response.text[:200]}")
    except Exception as e:
        print(f"   Erro: {e}")

    print("\n10. Fechando cliente...")
    await client.close()
    print("   ✓ Cliente fechado")


async def main():
    parser = argparse.ArgumentParser(description="GemRev Python - Exemplo Prático")
    parser.add_argument("--cookie", help="__Secure-1PSID cookie para autenticação")
    parser.add_argument("--proxy", help="Proxy HTTP (ex: http://localhost:8080)")
    parser.add_argument("--guest", action="store_true", help="Usar modo convidado (sem cookie)")
    parser.add_argument("--verbose", action="store_true", help="Log detalhado")
    args = parser.parse_args()

    if args.guest or not args.cookie:
        print("⚠  Usando modo convidado (funcionalidades limitadas)\n")
        await demo_guest_mode()
    else:
        await demo_auth_mode(args.cookie, args.proxy, args.verbose)


if __name__ == "__main__":
    asyncio.run(main())
