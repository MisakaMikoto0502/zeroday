import re
import asyncio
import discord

from discord import VoiceChannel
from discord.ext.commands import Context
from app.error.music import InvalidVoiceChannel
from app.error.music import VoiceConnectionError
from app.ext.music.YTDLSource import YTDLSource
from app.ext.music.option import EmbedSaftySearch
from app.ext.music.option import adult_filter
from app.controller.logger import Logger
from app.ext.music.option import (
    embed_ERROR,
    embed_queued,
    embed_value,
)


@Logger.set()
def cleanText(readData):
    text = re.sub('[-=+,#/\?:^$.@*\"※~&%ㆍ!』\\‘|\(\)\[\]\<\>`\'…》]', '', readData)
    return text


@Logger.set()
async def connect_voice_channel(ctx: Context, channel: VoiceChannel):
    """Voice Channel에 연결합니다.

    :param ctx: discord.ext.commands.Context
    :param channel: discord.VoiceChannel
    """
    if not channel:
        try:
            channel = ctx.author.voice.channel
        except AttributeError as r2:
            await ctx.send("'Voice channel'에 연결하지 못하였습니다.\n 유효한 'Voice channel'에 자신이 들어와 있는지 확인바랍니다.")
            raise InvalidVoiceChannel(f"{r2.__class__.__module__}: {r2.__class__.__name__}")

    vc = ctx.voice_client

    if vc:
        if vc.channel.id == channel.id:
            return
        try:
            await vc.move_to(channel)
        except asyncio.TimeoutError as TError:
            await ctx.send(f"Moving to channel: <{str(channel)}> timed out")
            raise VoiceConnectionError(f"{TError.__class__.__module__}: {TError.__class__.__name__}")
    else:
        try:
            await channel.connect()
        except asyncio.TimeoutError as TError2:
            await ctx.send(f"Connecting to channel: <{str(channel)}> timed out")
            raise VoiceConnectionError(f"{TError2.__class__.__module__}: {TError2.__class__.__name__}")

    return await ctx.send(
        "```css\nConnected to **{}**\n```".format(str(channel)), delete_after=10
    )


@Logger.set()
async def play_loop(this, ctx: Context, mode: str):
    """반복 재생

    :param this: self
    :param ctx: discord.ext.commands.Context
    :param mode: str
    """
    player = this.get_player(ctx)

    if not player:
        return

    modes = ["current", "all", "disable"]
    if not mode in modes:
        return await ctx.send(
            f"invalid arg: {mode}\nuse: {'/'.join(modes)}", delete_after=5
        )

    if mode == "disable":
        player.loop = False
    else:
        player.loop = True

    return await ctx.send(f"Player repeat: **{mode}**", delete_after=5)


@Logger.set()
async def play_music(this, ctx: Context, search: str):
    """재생

    :param this: self
    :param ctx: discord.ext.commands.Context
    :param search: str
    """
    await ctx.trigger_typing()
    vc = ctx.voice_client
    if not vc:
        await ctx.invoke(this.connect_)

    player = this.get_player(ctx)

    source = await this.check(ctx=ctx, search=search)

    if await adult_filter(search=cleanText(source.title), loop=ctx.bot.loop) == 1:
        embed_two = EmbedSaftySearch(data=str(search))
        await this.cleanup(ctx.guild)
        return await ctx.send(embed=embed_two)
    else:
        return [player, source]


@Logger.set()
async def play_youtube_playlist(this, ctx: Context, search: str):
    """유튜브 재생목록 재생

    :param this: self
    :param ctx: discord.ext.commands.Context
    :param search: str
    """
    await ctx.trigger_typing()

    vc = ctx.voice_client
    if not vc:
        await ctx.invoke(this.connect_)

    if await adult_filter(search=cleanText(search), loop=ctx.bot.loop) == 1:
        embed_two = EmbedSaftySearch(data=str(search))
        return await ctx.send(embed=embed_two)
    else:
        player = this.get_player(ctx)
        source = await YTDLSource.create_playlist(ctx, search, download=False, loop=ctx.bot.loop)
        for ix in source:
            xo = await player.queue.put(ix)
        return xo


@Logger.set()
async def pause_play(this, ctx: Context):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=embed_ERROR, delete_after=20)
    elif vc.is_paused():
        return

    nx = this.pause_embed(ctx=ctx)
    vc.pause()

    return await ctx.send(embed=nx, delete_after=5)


@Logger.set()
async def replay(this, ctx: Context):
    """Replay

    :param this: self
    :param ctx: discord.ext.commands.Context
    """
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return await ctx.send(embed=embed_ERROR, delete_after=20)
    elif not vc.is_paused():
        return

    nx = this.resume_embed(ctx=ctx)
    vc.resume()

    return await ctx.send(nx, delete_after=5)


@Logger.set()
async def skip_song(ctx: Context):
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return await ctx.send(embed=embed_ERROR, delete_after=20)

    if vc.is_paused():
        pass
    elif not vc.is_playing():
        return

    vc.stop()
    return await ctx.send(f"```css\n{ctx.author} : 스킵!.\n```", delete_after=5)


@Logger.set()
async def remove_song(this, ctx: Context, index: int):
    """remove song

    :param this: self
    :param ctx: discord.ext.commands.Context
    :param index: index of the playlist
    """
    player = this.get_player(ctx)
    if len(player.queue._queue) == 0:
        return await ctx.send("Empty queue", delete_after=10)

    player.queue.remove(index - 1)
    return await ctx.send("Success delete song", delete_after=10)


@Logger.set()
async def shuffle(this, ctx: Context):
    player = this.get_player(ctx)
    if len(player.queue._queue) == 0:
        return await ctx.send("Empty queue", delete_after=10)

    player.queue.shuffle()
    return await ctx.send("Success")


@Logger.set()
async def get_playlist(this, ctx: Context):
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return await ctx.send(embed=embed_ERROR, delete_after=20)

    player = this.get_player(ctx)
    if player.queue.empty():
        return await ctx.send(embed=embed_queued)

    ox = await this.queue_info_embed(player=player)
    return await ctx.send(embed=ox)


@Logger.set()
async def playing_song(this, ctx: Context):
    """재생중인 컨텐츠 정보 보기

    :param this: self
    :param ctx: discord.ext.commands.Context
    """
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return await ctx.send(embed=embed_ERROR, delete_after=20)

    player = this.get_player(ctx)
    if not player.current:
        return await ctx.send(embed=embed_ERROR)

    try:
        await player.np.delete()
    except discord.HTTPException:
        pass

    ex = await this.now_playing_embed(vc=vc)
    player.np = await ctx.send(embed=ex)


@Logger.set()
async def change_player_volume(this, ctx: Context, vol: float):
    """volume 조절

    :param this: self
    :param ctx: discord.ext.commands.Context
    :param vol: volume
    """

    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return await ctx.send(embed=embed_ERROR, delete_after=10)

    if not 0 < vol < 101:
        return await ctx.send(embed_value)

    player = this.get_player(ctx)

    if vc.source:
        vc.source.volume = vol / 100

    player.volume = vol / 100
    ix = await this.volume_embed(ctx=ctx, vol=vol)
    return await ctx.send(embed=ix, delete_after=10)


@Logger.set()
async def play_stop(this, ctx: Context):
    """재생종료

    :param this: self
    :param ctx: discord.ext.commands.Context
    """
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return await ctx.send(embed=embed_ERROR, delete_after=20)

    await this.cleanup(ctx.guild)
