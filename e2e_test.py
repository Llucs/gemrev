"""
Teste end-to-end completo da GemRev Python.

Este script testa todas as funcionalidades principais contra o Gemini real.
Requer o cookie __Secure-1PSID para testes autenticados.

Uso:
  python3 e2e_test.py                        # Modo convidado
  python3 e2e_test.py --cookie "SEU_COOKIE"  # Autenticado
  python3 e2e_test.py --cookie "SEU_COOKIE" --all  # Testa TUDO (incluindo gems, histórico, etc)
"""

import asyncio
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gemrev import Gemini, Model


async def test_guest_basic():
    print("\n[TEST] guest_basic")
    client = Gemini()
    chat = client.new_chat()

    resp = await chat.generate_content(prompt="Say 'hello' in one word.")
    text = resp.text.strip().lower()
    assert 'hello' in text, f"Expected 'hello' in response, got: {text[:100]}"
    assert resp.cid
    assert resp.rid
    print(f"  ✓ Texto: {resp.text[:100]}")
    print(f"  ✓ CID: {resp.cid}")
    print(f"  ✓ RID: {resp.rid}")
    print(f"  ✓ Candidates: {len(resp.candidates)}")


async def test_guest_multiturn():
    print("\n[TEST] guest_multiturn")
    client = Gemini()
    chat = client.new_chat()

    r1 = await chat.generate_content(prompt="Remember the codeword: ZEPHYR.")
    print(f"  ✓ Turno 1: {r1.text[:80]}")

    r2 = await chat.generate_content(prompt="What was the codeword?")
    assert 'zephyr' in r2.text.lower(), f"Expected 'zephyr' in turn 2, got: {r2.text[:100]}"
    print(f"  ✓ Turno 2 (lembrou): {r2.text[:100]}")


async def test_guest_streaming():
    print("\n[TEST] guest_streaming")
    client = Gemini()
    chat = client.new_chat()

    chunks = []
    async for chunk in chat.generate_content_stream(prompt="Count 1 to 5."):
        chunks.append(chunk)
        if chunk.text_delta:
            print(f"  Δ: {chunk.text_delta[:60]}")

    assert len(chunks) > 0
    final = chunks[-1]
    assert final.text
    print(f"  ✓ Streaming concluído: {len(chunks)} chunks")
    print(f"  ✓ Texto final: {final.text[:100]}")


async def test_auth_basic(cookie, proxy=None):
    print("\n[TEST] auth_basic")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()
    print("  ✓ Init OK")

    chat = client.new_chat(model=Model.BASIC_FLASH)
    resp = await chat.generate_content(prompt="What is 2+2? Answer with just the number.")
    assert '4' in resp.text.strip(), f"Expected 4, got: {resp.text[:100]}"
    print(f"  ✓ Resposta: {resp.text[:100]}")


async def test_auth_streaming(cookie, proxy=None):
    print("\n[TEST] auth_streaming")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()

    chat = client.new_chat(model=Model.BASIC_FLASH)
    chunks = []
    async for chunk in chat.generate_content_stream(prompt="Write a short poem about Python."):
        chunks.append(chunk)

    assert len(chunks) > 0
    print(f"  ✓ Streaming: {len(chunks)} chunks, texto: {chunks[-1].text[:100]}")


async def test_auth_multiturn(cookie, proxy=None):
    print("\n[TEST] auth_multiturn")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()

    chat = client.new_chat(model=Model.BASIC_FLASH)

    r1 = await chat.generate_content(prompt="My name is Alice.")
    print(f"  ✓ Turno 1: {r1.text[:80]}")

    r2 = await chat.generate_content(prompt="What is my name?")
    assert 'alice' in r2.text.lower(), f"Expected 'Alice' in response: {r2.text[:100]}"
    print(f"  ✓ Turno 2: {r2.text[:100]}")


async def test_auth_models(cookie, proxy=None):
    print("\n[TEST] auth_models")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()

    models = await client.models()
    assert len(models) > 0
    print(f"  ✓ {len(models)} modelos encontrados:")
    for m in models:
        print(f"    - {m.model_name} ({m.display_name})")


async def test_auth_chats(cookie, proxy=None):
    print("\n[TEST] auth_chats")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()

    chats = await client.chats()
    print(f"  ✓ {len(chats)} conversas recentes")
    for c in chats[:3]:
        print(f"    - {c.get('title', 'sem título')} [{c.get('cid', '')[:20]}...]")


async def test_auth_gems(cookie, proxy=None):
    print("\n[TEST] auth_gems")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()

    gems = await client.gems()
    print(f"  ✓ {len(gems)} gems encontradas")
    for g in gems[:3]:
        print(f"    - {g['name']} {'[predefinida]' if g['predefined'] else '[custom]'}")


async def test_auth_extended_thinking(cookie, proxy=None):
    print("\n[TEST] auth_extended_thinking")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()

    chat = client.new_chat(model=Model.BASIC_FLASH)
    resp = await chat.generate_content(
        prompt="Solve: 17 * 23 = ? Show your reasoning.",
        extended_thinking=True,
    )
    if resp.thoughts:
        print(f"  ✓ Thoughts: {resp.thoughts[:200]}")
    print(f"  ✓ Resposta: {resp.text[:200]}")


async def test_auth_temp_chat(cookie, proxy=None):
    print("\n[TEST] auth_temp_chat")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()

    chat = client.new_chat(model=Model.BASIC_FLASH, temporary=True)
    resp = await chat.generate_content(prompt="Say 'temporary chat works'.")
    assert 'temporary' in resp.text.lower(), f"Expected 'temporary', got: {resp.text[:100]}"
    print(f"  ✓ Temp chat: {resp.text[:100]}")


async def test_auth_ask(cookie, proxy=None):
    print("\n[TEST] auth_ask (one-shot)")
    client = Gemini(secure_1psid=cookie, proxy=proxy)
    await client.init()

    resp = await client.ask("What is the capital of France?", model=Model.BASIC_FLASH, temporary=True)
    assert 'paris' in resp.text.lower(), f"Expected 'Paris', got: {resp.text[:100]}"
    print(f"  ✓ Ask: {resp.text[:100]}")


async def run_guest_tests():
    print("\n" + "=" * 60)
    print("TESTES MODO CONVIDADO")
    print("=" * 60)
    tests = [test_guest_basic, test_guest_multiturn, test_guest_streaming]
    passed = 0
    for test in tests:
        try:
            await test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
    print(f"\nGuest: {passed}/{len(tests)} passaram")
    return passed == len(tests)


async def run_auth_tests(cookie, proxy=None, all_tests=False):
    print("\n" + "=" * 60)
    print("TESTES MODO AUTENTICADO")
    print("=" * 60)

    basic_tests = [
        test_auth_basic,
        test_auth_streaming,
        test_auth_multiturn,
        test_auth_models,
    ]

    all_auth_tests = basic_tests + [
        test_auth_chats,
        test_auth_gems,
        test_auth_extended_thinking,
        test_auth_temp_chat,
        test_auth_ask,
    ]

    tests_to_run = all_auth_tests if all_tests else basic_tests
    passed = 0
    for test in tests_to_run:
        try:
            await test(cookie, proxy)
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nAuth: {passed}/{len(tests_to_run)} passaram")
    return passed == len(tests_to_run)


async def main():
    parser = argparse.ArgumentParser(description="GemRev E2E Tests")
    parser.add_argument("--cookie", help="__Secure-1PSID cookie")
    parser.add_argument("--proxy", help="Proxy HTTP")
    parser.add_argument("--all", action="store_true", help="Testar todas as funcionalidades")
    args = parser.parse_args()

    all_ok = True

    if args.cookie:
        ok = await run_auth_tests(args.cookie, args.proxy, args.all)
        all_ok = all_ok and ok

    ok = await run_guest_tests()
    all_ok = all_ok and ok

    print("\n" + "=" * 60)
    if all_ok:
        print("RESULTADO: ✅ Todos os testes passaram!")
    else:
        print("RESULTADO: ❌ Alguns testes falharam")
    print("=" * 60)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
