from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from discord import Message, utils
from peewee import (
    CharField,
    DatabaseError,
    DoesNotExist,
    Field,
    ForeignKeyField,
    IntegerField,
    IntegrityError,
    Model,
    SqliteDatabase,
)

if sys.version_info >= (3, 11):
    from enum import StrEnum, auto
else:
    from enum import auto

    from backports.strenum import StrEnum

if TYPE_CHECKING:
    from utils.context import Context

logger = logging.getLogger("info")
error_logger = logging.getLogger("error")

DB = "data/club_moderation.db"
db = SqliteDatabase(DB, pragmas={'foreign_keys': 1})


class ClubActivities(StrEnum):
    CREATE = auto()
    PING = auto()
    JOIN = auto()
    LEAVE = auto()
    DELETE = auto()


class TimestampTzField(Field):
    field_type = 'TEXT'

    def db_value(self, value: datetime) -> str:
        if value:
            return value.isoformat()
        else:
            return ''

    def python_value(self, value: str) -> Optional[datetime]:
        if value:
            return datetime.fromisoformat(value)
        else:
            return None


class BaseModel(Model):
    class Meta:
        database = db


class ClubModeration(BaseModel):
    id = IntegerField(primary_key=True)


class DiscordLink(BaseModel):
    guild_id = IntegerField()
    channel_id = IntegerField()
    message_id = IntegerField()
    link_datetime = TimestampTzField(default=datetime.now(tz=timezone.utc))


class ClubHistory(BaseModel):
    id = IntegerField(primary_key=True)
    actions = CharField(
        choices=[(activities, activities) for activities in ClubActivities]
    )
    author_id = IntegerField()
    author_name = CharField()
    club_name = CharField()
    discord_link = ForeignKeyField(DiscordLink, backref="link")
    history_datetime = TimestampTzField(default=datetime.now(tz=timezone.utc))

    @property
    def check_if_within_24_hours(self) -> bool:
        now = datetime.now(timezone.utc)
        old: datetime = self.history_datetime
        return now.day - old.day < 1

    @property
    def time_stamp(self):
        ts = utils.format_dt(self.history_datetime, style='R')
        return ts


db.create_tables([ClubHistory, DiscordLink])


def save_join_or_leave_history(
        ctx: Context,
        club_name: str,
        join: bool
):
    club_action = ClubActivities.JOIN if join else ClubActivities.LEAVE
    link = DiscordLink.create(
        guild_id=ctx.guild.id,
        channel_id=ctx.channel.id,
        message_id=ctx.message.id
    )
    ClubHistory.create(
        author_id=ctx.author.id,
        author_name=ctx.author.name,
        club_name=club_name,
        actions=club_action,
        discord_link=link,
    )


def save_create_history(
        ctx: Context,
        club_name: str
):
    link = DiscordLink.create(
        guild_id=ctx.guild.id,
        channel_id=ctx.channel.id,
        message_id=ctx.message.id
    )
    ClubHistory.create(
        author_id=ctx.author.id,
        author_name=ctx.author.name,
        club_name=club_name,
        actions=ClubActivities.CREATE,
        discord_link=link,
    )


def save_delete_history(
        ctx: Context,
        club_name: str
):
    link = DiscordLink.create(
        guild_id=ctx.guild.id,
        channel_id=ctx.channel.id,
        message_id=ctx.message.id
    )
    ClubHistory.create(
        author_id=ctx.author.id,
        author_name=ctx.author.name,
        club_name=club_name,
        actions=ClubActivities.DELETE,
        discord_link=link,
    )


def save_ping_history(
        ctx: Context,
        message: Message,
        club_name: str
):
    link = DiscordLink.create(
        guild_id=ctx.guild.id,
        channel_id=ctx.channel.id,
        message_id=message.id,
    )
    ClubHistory.create(
        author_id=ctx.author.id,
        author_name=ctx.author.name,
        club_name=club_name,
        actions=ClubActivities.PING,
        discord_link=link,
    )


def get_the_last_entry_from_club_name_from_guild(
        club_name: str,
        guild_id: int
) -> Optional[ClubHistory]:
    try:
        last_entry = ClubHistory.select().join(DiscordLink).\
            where(ClubHistory.club_name == club_name and
                  DiscordLink.guild_id == guild_id and
                  ClubHistory.actions == ClubActivities.PING
                  ).order_by(
                ClubHistory.id.desc()
        ).get()

        return last_entry
    except DoesNotExist:
        return None
    except IntegrityError:
        trace = traceback.format_exc()
        error_logger.error(trace)
        return None
    except DatabaseError:
        trace = traceback.format_exc()
        error_logger.error(trace)
        return None
