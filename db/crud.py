"""
Asynchronous CRUD operations for users, groups, messages, and state tables.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Group, Message, State, User


# =====================================================================
# User Operations
# =====================================================================
async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    stmt = select(User).where(User.telegram_id == telegram_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_all_active_users(session: AsyncSession) -> List[User]:
    stmt = select(User).where(User.is_active.is_(True), User.is_banned.is_(False))
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_users(session: AsyncSession, limit: int = 50, offset: int = 0) -> List[User]:
    stmt = select(User).order_by(User.id.desc()).limit(limit).offset(offset)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    encrypted_phone: str,
    api_key_index: int = 0,
    is_admin: bool = False,
) -> User:
    user = User(
        telegram_id=telegram_id,
        username=username,
        phone=encrypted_phone,
        api_key_index=api_key_index,
        is_active=True,
        is_banned=False,
        is_admin=is_admin,
    )
    session.add(user)
    await session.flush()

    # Create initial state record
    default_state = State(user_id=user.id)
    session.add(default_state)
    await session.flush()

    return user


async def update_user_last_seen(session: AsyncSession, user_id: int):
    stmt = update(User).where(User.id == user_id).values(last_seen=datetime.utcnow())
    await session.execute(stmt)


async def set_user_ban_status(session: AsyncSession, telegram_id: int, is_banned: bool) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return False
    user.is_banned = is_banned
    if is_banned and user.state:
        user.state.is_sending = False
    return True


async def get_system_stats(session: AsyncSession) -> Dict[str, int]:
    total_users = (await session.execute(select(func.count(User.id)))).scalar_one() or 0
    active_users = (
        await session.execute(
            select(func.count(User.id)).where(User.is_active.is_(True), User.is_banned.is_(False))
        )
    ).scalar_one() or 0
    banned_users = (
        await session.execute(select(func.count(User.id)).where(User.is_banned.is_(True)))
    ).scalar_one() or 0
    total_groups = (await session.execute(select(func.count(Group.id)))).scalar_one() or 0
    total_messages = (await session.execute(select(func.count(Message.id)))).scalar_one() or 0

    return {
        "total_users": total_users,
        "active_users": active_users,
        "banned_users": banned_users,
        "total_groups": total_groups,
        "total_messages": total_messages,
    }


# =====================================================================
# Group Operations
# =====================================================================
async def get_user_groups(session: AsyncSession, user_id: int) -> List[Group]:
    stmt = select(Group).where(Group.user_id == user_id, Group.is_active.is_(True)).order_by(Group.id.asc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def add_group(
    session: AsyncSession,
    user_id: int,
    group_identifier: str,
    title: str = "",
) -> Tuple[bool, str, int]:
    clean = group_identifier.strip()
    if "t.me/" in clean:
        clean = clean.split("t.me/")[-1].strip("/")

    # Check for duplicate
    stmt = select(Group).where(Group.user_id == user_id, Group.group_identifier == clean)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.title = title or existing.title
            groups = await get_user_groups(session, user_id)
            return True, f"Guruh qayta faollashtirildi: {clean}", len(groups)
        groups = await get_user_groups(session, user_id)
        return False, f"Guruh allaqachon mavjud: {clean}", len(groups)

    new_group = Group(user_id=user_id, group_identifier=clean, title=title, is_active=True)
    session.add(new_group)
    await session.flush()

    groups = await get_user_groups(session, user_id)
    return True, f"Guruh qo'shildi: {clean}", len(groups)


async def remove_group(session: AsyncSession, user_id: int, group_identifier: str) -> Tuple[bool, str, int]:
    clean = group_identifier.strip()
    if "t.me/" in clean:
        clean = clean.split("t.me/")[-1].strip("/")

    stmt = select(Group).where(Group.user_id == user_id, Group.group_identifier == clean)
    group = (await session.execute(stmt)).scalar_one_or_none()
    if not group:
        groups = await get_user_groups(session, user_id)
        return False, f"Bunday guruh topilmadi: {clean}", len(groups)

    await session.delete(group)
    await session.flush()
    groups = await get_user_groups(session, user_id)
    return True, f"Guruh o'chirildi: {clean}", len(groups)


# =====================================================================
# Message Operations
# =====================================================================
async def get_user_messages(session: AsyncSession, user_id: int) -> List[Message]:
    stmt = select(Message).where(Message.user_id == user_id, Message.is_active.is_(True)).order_by(Message.position.asc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def add_message(session: AsyncSession, user_id: int, text: str) -> Tuple[bool, str, int]:
    clean = text.strip()
    if not clean:
        messages = await get_user_messages(session, user_id)
        return False, "Xabar matni bo'sh bo'lishi mumkin emas.", len(messages)

    current = await get_user_messages(session, user_id)
    new_pos = len(current)

    msg = Message(user_id=user_id, text=clean, position=new_pos, is_active=True)
    session.add(msg)
    await session.flush()

    updated = await get_user_messages(session, user_id)
    return True, "Yangi xabar shabloni saqlandi!", len(updated)


async def remove_message_by_index(session: AsyncSession, user_id: int, index_1based: int) -> Tuple[bool, str, int]:
    messages = await get_user_messages(session, user_id)
    if not messages:
        return False, "Xabarlar ro'yxati bo'sh.", 0

    if index_1based < 1 or index_1based > len(messages):
        return False, f"Noto'g'ri indeks. 1 dan {len(messages)} gacha son kiriting.", len(messages)

    target_msg = messages[index_1based - 1]
    await session.delete(target_msg)
    await session.flush()

    # Reorder remaining positions
    remaining = await get_user_messages(session, user_id)
    for idx, m in enumerate(remaining):
        m.position = idx
    await session.flush()

    return True, f"Xabar #{index_1based} o'chirildi.", len(remaining)


# =====================================================================
# State Operations
# =====================================================================
async def get_or_create_state(session: AsyncSession, user_id: int) -> State:
    stmt = select(State).where(State.user_id == user_id)
    state = (await session.execute(stmt)).scalar_one_or_none()
    if not state:
        state = State(user_id=user_id)
        session.add(state)
        await session.flush()
    return state


async def update_user_state(session: AsyncSession, user_id: int, **kwargs) -> State:
    state = await get_or_create_state(session, user_id)
    for key, val in kwargs.items():
        if hasattr(state, key):
            setattr(state, key, val)
    await session.flush()
    return state
