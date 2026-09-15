import re

from .connectome_client import ConnectomeClient, format_relationship
from .identity import discord_entity_id

# The relationship predicate linking a player entity to the PC entity they
# currently play. Exercises supersede_relationship (1.1B) for real: retiring
# a PC patches this predicate's prior entry rather than deleting it.
PLAYS_PREDICATE = "plays"
CHARACTER_KIND = "character"
OWNER_META_KEY = "owner"

# Design decision (see issue #45): party `member_of` lives on the character
# entity, not the player (1.1a-2), so retiring a PC does NOT carry its party
# membership over to the new one. A player who wants their new PC in the
# party has to run /join-party again - silent inheritance would let a party
# gain a member it never actually admitted.
PARTY_MEMBERSHIP_CARRIES_OVER = False


def slugify_pc_name(name: str) -> str:
    """Slugify a PC name into the id used for its ent_<id>.json entity record."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("PC name must contain at least one alphanumeric character")
    return slug


class PlayerState:
    """Per-player cache of the PC a player currently plays.

    There is no entity-lookup tool yet (Phase 2) to recover "which memory
    asserted this player's current `plays` relationship" from the backend, so
    the bot caches the memory id itself at write time (see identity.py's
    discord_entity_id docstring for the same constraint). This is in-process
    state: it does not survive a bot restart.
    """

    def __init__(self) -> None:
        self._current: dict[str, dict[str, str]] = {}

    def get(self, player_id: str) -> dict[str, str] | None:
        return self._current.get(player_id)

    def set(self, player_id: str, pc_id: str, memory_id: str) -> None:
        self._current[player_id] = {"pc_id": pc_id, "memory_id": memory_id}


async def handle_play_character(
    connectome: ConnectomeClient,
    state: PlayerState,
    user_id: int,
    pc_name: str,
) -> str:
    """Resolve-or-create a PC entity and record that the calling player plays it.

    Refuses if another player already owns a PC with this name. If the caller
    already plays a different PC, that PC's `plays` relationship is
    superseded by this one (retirement) - party membership is not carried
    over, per PARTY_MEMBERSHIP_CARRIES_OVER above.
    """
    player_id = discord_entity_id(user_id)
    pc_id = slugify_pc_name(pc_name)

    existing_entity = await connectome.get_entity(pc_id)
    owner: object = None
    if existing_entity is not None:
        meta = existing_entity.get("meta")
        if isinstance(meta, dict):
            owner = meta.get(OWNER_META_KEY)
    if owner is not None and owner != player_id:
        return f"**{pc_name}** is already played by someone else."

    current = state.get(player_id)
    if owner == player_id and current is not None and current["pc_id"] == pc_id:
        return f"You're already playing **{pc_name}**."

    if existing_entity is None:
        await connectome.create_entity(pc_id, kind=CHARACTER_KIND, meta={OWNER_META_KEY: player_id})

    result = await connectome.remember(
        f"{player_id} plays {pc_name}.",
        entities=[player_id, pc_id],
        relationships=[format_relationship(player_id, PLAYS_PREDICATE, pc_id)],
    )
    new_memory_id = result["key"]

    retired = current is not None and current["pc_id"] != pc_id
    if retired and current is not None:
        _ = await connectome.supersede_relationship(
            memory_id=current["memory_id"],
            subject_entity_id=player_id,
            predicate=PLAYS_PREDICATE,
            object_entity_id=current["pc_id"],
            superseded_by=new_memory_id,
        )

    state.set(player_id, pc_id, new_memory_id)

    if retired:
        return (
            f"Your previous character retires. You're now playing **{pc_name}**. "
            "Party membership doesn't carry over - run /join-party again if it needs to be in one."
        )
    return f"You're now playing **{pc_name}**."
