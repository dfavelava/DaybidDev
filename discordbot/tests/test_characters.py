import pytest

from discordbot.characters import PlayerState, handle_play_character, slugify_pc_name
from discordbot.identity import discord_entity_id


class FakeConnectomeClient:
    def __init__(self) -> None:
        self.entities: dict[str, dict[str, object]] = {}
        self.memories: list[dict[str, object]] = []
        self.supersede_calls: list[dict[str, object]] = []
        self._next_memory_id = 0

    async def get_entity(self, entity_id: str) -> dict[str, object] | None:
        return self.entities.get(entity_id)

    async def create_entity(self, entity_id: str, kind=None, meta=None, name=None) -> None:
        self.entities[entity_id] = {"id": entity_id, "kind": kind, "meta": meta, "name": name}

    async def remember(self, content: str, entities=None, relationships=None, **kwargs) -> dict[str, str]:
        self._next_memory_id += 1
        key = f"mem_{self._next_memory_id}.md"
        self.memories.append({"key": key, "content": content, "entities": entities, "relationships": relationships})
        return {"key": key}

    async def supersede_relationship(self, memory_id, subject_entity_id, predicate, object_entity_id=None, superseded_by=None):
        self.supersede_calls.append(
            {
                "memory_id": memory_id,
                "subject_entity_id": subject_entity_id,
                "predicate": predicate,
                "object_entity_id": object_entity_id,
                "superseded_by": superseded_by,
            }
        )
        return {"message": "success"}


def test_slugify_pc_name():
    assert slugify_pc_name("Thorin") == "thorin"
    assert slugify_pc_name("  Thorin Oakenshield! ") == "thorin-oakenshield"


def test_slugify_pc_name_rejects_empty():
    with pytest.raises(ValueError):
        slugify_pc_name("!!!")


async def test_play_character_creates_pc_entity_and_relationship():
    connectome = FakeConnectomeClient()
    state = PlayerState()

    message = await handle_play_character(connectome, state, user_id=1, pc_name="Thorin")

    assert connectome.entities["thorin"]["kind"] == "character"
    assert connectome.entities["thorin"]["meta"] == {"owner": "discord-1"}
    assert len(connectome.memories) == 1
    assert connectome.memories[0]["relationships"] == [
        {
            "subjectEntityId": "discord-1",
            "predicate": "plays",
            "objectEntityId": "thorin",
            "kind": "fact",
            "superseded_by": None,
        }
    ]
    assert "Thorin" in message
    assert state.get("discord-1") == {"pc_id": "thorin", "memory_id": connectome.memories[0]["key"]}


async def test_play_character_refuses_when_owned_by_another_player():
    connectome = FakeConnectomeClient()
    state = PlayerState()
    _ = await handle_play_character(connectome, state, user_id=1, pc_name="Thorin")

    message = await handle_play_character(connectome, state, user_id=2, pc_name="Thorin")

    assert "already played by someone else" in message
    assert len(connectome.memories) == 1
    assert state.get(discord_entity_id(2)) is None


async def test_play_character_rerun_by_owner_is_noop():
    connectome = FakeConnectomeClient()
    state = PlayerState()
    _ = await handle_play_character(connectome, state, user_id=1, pc_name="Thorin")

    message = await handle_play_character(connectome, state, user_id=1, pc_name="Thorin")

    assert "already playing" in message
    assert len(connectome.memories) == 1
    assert connectome.supersede_calls == []


async def test_play_character_retires_previous_pc_on_switch():
    connectome = FakeConnectomeClient()
    state = PlayerState()
    _ = await handle_play_character(connectome, state, user_id=1, pc_name="Thorin")
    old_memory_id = connectome.memories[0]["key"]

    message = await handle_play_character(connectome, state, user_id=1, pc_name="Balin")

    assert len(connectome.memories) == 2
    new_memory_id = connectome.memories[1]["key"]
    assert connectome.supersede_calls == [
        {
            "memory_id": old_memory_id,
            "subject_entity_id": "discord-1",
            "predicate": "plays",
            "object_entity_id": "thorin",
            "superseded_by": new_memory_id,
        }
    ]
    assert state.get("discord-1") == {"pc_id": "balin", "memory_id": new_memory_id}
    assert "retires" in message
