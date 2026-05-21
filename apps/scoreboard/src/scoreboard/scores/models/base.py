from __future__ import annotations

from tortoise import Model


class BaseScoreboardModel(Model):
    class Meta:
        abstract = True
