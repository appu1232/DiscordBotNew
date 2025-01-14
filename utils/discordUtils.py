import asyncio
import datetime
import logging
import os
import random
import re
import traceback

import aiohttp
import discord
from discord import Embed
from discord import File

from models.antiraid import ArGuild
from models.bot import BotBlacklist, BotBanlist
from models.moderation import (Reminderstbl, Actions)
from models.serversetup import SSManager
from utils.SimplePaginator import SimplePaginator

logger = logging.getLogger('info')
error_logger = logging.getLogger('error')


def bot_pfx(bot, _message):
    """
    :param bot: The bot
    :param _message: Preferrably mesage,
    if there is none use something that has the guild in it under .guild
    :return: prefix
    """
    prefix = bot.config['BOT_PREFIX']
    if hasattr(_message, 'channel') and isinstance(_message.channel, discord.DMChannel): return prefix
    gid = str(_message.guild.id)
    if gid not in bot.config['B_PREF_GUILD']: return prefix
    return bot.config['B_PREF_GUILD'][gid]


def bot_pfx_by_gid(bot, gid):
    prefix = bot.config['BOT_PREFIX']
    if str(gid) not in bot.config['B_PREF_GUILD']: return prefix
    return bot.config['B_PREF_GUILD'][str(gid)]


def bot_pfx_by_ctx(ctx):
    bot = ctx.bot
    gid = ctx.guild.id
    prefix = bot.config['BOT_PREFIX']
    if str(gid) not in bot.config['B_PREF_GUILD']: return prefix
    return bot.config['B_PREF_GUILD'][str(gid)]


def escape_at(content):
    return content.replace('@', '@\u200b')


async def getChannel(ctx, arg, silent=False):
    channels = []
    channel = arg.strip()
    if channel.startswith("<#") and channel.endswith(">"):
        chan = ctx.guild.get_channel(int(channel[2:-1]))
        if chan:
            channels.append(chan)
    else:
        for chan in ctx.guild.text_channels:
            if chan.name == channel or str(chan.id) == channel:
                if chan.permissions_for(ctx.author).read_messages:
                    channels.append(chan)
                    break
    NOT_FOUND = "The specified channel could not be found."
    if not channels:
        if not silent:
            await ctx.send(NOT_FOUND)
        return None

    chan = channels[0]

    permissions = chan.permissions_for(ctx.author)
    if not permissions.read_messages:
        await ctx.send(NOT_FOUND)
        return None

    return chan


def getEmbedFromMsg(msg):
    em = Embed(color=msg.author.color,
               timestamp=msg.created_at,
               description=f'{msg.content}\n\n[Jump to message]({msg.jump_url})')
    if len(msg.attachments) == 1:
        em.set_image(url=msg.attachments[0].url)
    if len(msg.attachments) > 1:
        em = Embed(color=msg.author.color,
                   timestamp=msg.created_at,
                   description=f'{msg.content}\n\n[Jump to message]({msg.jump_url})\n'
                               f'**🖼️ (Post contains multiple images, '
                               f'displaying only the first one)**')
        em.set_image(url=msg.attachments[0].url)

    em.set_author(name=msg.author.name, icon_url=msg.author.display_avatar.url)
    if not hasattr(msg.channel, 'name'):
        em.set_footer(text='Direct message')
    else:
        em.set_footer(text=f'#{msg.channel.name}')
    pic = str(msg.content).find('http')
    if pic > -1 and len(msg.attachments) == 0:
        urls = re.findall(r'https?:[/.\w\s-]*\.(?:jpg|gif|png|jpeg)', str(msg.content))
        if len(urls) > 0: em.set_image(url=urls[0])
    return em


def cleanUpBannedWords(bannerWordsArr, text):
    # bannedWords = ['@everyone', '@here']

    text = re.sub(r'`', '', text)

    for word in bannerWordsArr:
        if word in text:
            text = re.sub(rf'{word}', f'`{word}`', text)

    return text


async def print_hastebin_or_file(ctx, result, just_file=True):
    haste_failed = False
    if len(result) > 1950:
        if not just_file:
            try:
                m = await ctx.send('Trying to upload to hastebin, this might take a bit')
                async with aiohttp.ClientSession() as session:
                    async with session.post("https://hastebin.com/documents", data=str(result).encode('utf-8')) as resp:
                        if resp.status == 200:
                            haste_out = await resp.json()
                            url = "https://hastebin.com/" + haste_out["key"]
                            result = 'Large output. Posted to Hastebin: %s' % url
                            await m.delete()
                            return await ctx.send(result)
                        else:
                            await m.delete()
                            raise
            except:
                haste_failed = True
        if haste_failed or just_file:
            file = str(int(datetime.datetime.utcnow().timestamp()) - random.randint(100, 100000))
            with open(f"tmp/{file}.txt", "w", encoding='utf-8') as f:
                f.write(str(result))
            with open(f"tmp/{file}.txt", "rb") as f:
                py_output = File(f, f"{file}.txt")
                await ctx.send(
                    # content="Error posting to hastebin. Uploaded output to file instead.",
                    content="Uploaded output to file since the content is too long.",
                    file=py_output)
            try:
                os.remove(f"tmp/{file}.txt")
            except:
                error_logger.error(f"tmp/{file}.txt")
    else:
        return await ctx.send(result)


async def result_printer(ctx, result):
    if len(str(result)) > 2000:
        with open(f"tmp/{ctx.message.id}.txt", "w", encoding='utf-8') as f:
            f.write(str(result.strip("```")))
        with open(f"tmp/{ctx.message.id}.txt", "rb") as f:
            py_output = File(f, "output.txt")
            await ctx.send(content="uploaded output to file since output was too long.", file=py_output)
            os.remove(f"tmp/{ctx.message.id}.txt")
    else:
        await ctx.send(result)


def getParts2kByDelimiter(text, delimi, extra='', limit=1900):
    ret = []
    arr = text.split(delimi)
    i = -1
    while arr:
        i += 1
        txt = ''
        while len(txt) < limit:
            if not arr: break
            txt += (arr[0] + delimi)
            del arr[0]
        txt = txt[:len(txt) - len(delimi)]
        if i > 0: txt = extra + txt
        if txt != '': ret.append(txt)
    return ret


def getEmbedsFromTxtArrs(bot, arrs, title, color=None, cnt_join_instd_of_spc=None, split_by=' '):
    embeds = []
    for a in arrs:
        if cnt_join_instd_of_spc:
            a = cnt_join_instd_of_spc.join(a.split(split_by))
        embeds.append(Embed(title=f'{title}\n'
                                  f'Page {len(embeds) + 1}/[MAX]', description=a,
                            color=bot.config['BOT_DEFAULT_EMBED_COLOR'] if not color else color))
    for e in embeds:
        e.title = str(e.title).replace("[MAX]", str(len(embeds)))
    return embeds


async def send_and_maybe_paginate_embeds(ctx, embeds):
    if len(embeds) == 1:
        await ctx.send(embed=embeds[0])
    else:
        await SimplePaginator(extras=embeds).paginate(ctx)


async def saveFile(link, path, fName):
    fileName = f"{path}/{fName}"
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as r:
            with open(fileName, 'wb') as fd:
                async for data in r.content.iter_chunked(1024):
                    fd.write(data)
    return fileName


async def prompt(ctx, message, *, timeout=60.0, delete_after=True, reactor_id=None):
    """An interactive reaction confirmation dialog.
    Parameters
    -----------
    ctx: any
        context from bot
    message: str
        The message to show along with the prompt.
    timeout: float
        How long to wait before returning.
    delete_after: bool
        Whether to delete the confirmation message after we're done.
    reactor_id: Optional[int]
        The member who should respond to the prompt. Defaults to the author of the
        Context's message.
    Returns
    --------
    Optional[bool]
        ``True`` if explicit confirm,
        ``False`` if explicit deny,
        ``None`` if deny due to timeout
    """

    if not ctx.channel.permissions_for(ctx.me).add_reactions:
        raise RuntimeError('Bot does not have Add Reactions permission.')

    fmt = f'{message}\n\nReact with \N{WHITE HEAVY CHECK MARK} to confirm or \N{CROSS MARK} to deny.'

    reactor_id = reactor_id or ctx.author.id
    msg = await ctx.send(fmt)

    confirm = None

    def check(payload):
        nonlocal confirm

        if payload.message_id != msg.id or payload.user_id != reactor_id:
            return False

        codepoint = str(payload.emoji)

        if codepoint == '\N{WHITE HEAVY CHECK MARK}':
            confirm = True
            return True
        elif codepoint == '\N{CROSS MARK}':
            confirm = False
            return True

        return False

    for emoji in ('\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}'):
        await msg.add_reaction(emoji)

    try:
        await ctx.bot.wait_for('raw_reaction_add', check=check, timeout=timeout)
    except asyncio.TimeoutError:
        confirm = None

    try:
        if delete_after:
            await msg.delete()
    finally:
        return confirm


async def prompt_custom(ctx, message, *, emotes=None, timeout=60.0, delete_after=True, reactor_id=None):
    """Similar to prompt but you make your own message and emotes
    emotes length shouldn't be less than 1 and more than 19!!! (be careful!)

    Returns reactex index or -1 if X
    """
    if not emotes or len(emotes) == 0: return
    if not ctx.channel.permissions_for(ctx.me).add_reactions:
        raise RuntimeError('Bot does not have Add Reactions permission.')

    # fmt = f'{message}\n\nReact with \N{WHITE HEAVY CHECK MARK} to confirm or \N{CROSS MARK} to deny.'
    fmt = f'{message}\n\nReact with one of {" ".join(emotes)} to select your choice. React with ❌ to cancel this.'

    reactor_id = reactor_id or ctx.author.id
    msg = await ctx.send(fmt)

    confirm = None

    def check(payload):
        nonlocal confirm

        if payload.message_id != msg.id or payload.user_id != reactor_id:
            return False

        codepoint = str(payload.emoji)

        if codepoint in emotes:
            confirm = emotes.index(codepoint)
            return True
        elif codepoint == '❌':
            confirm = -1
            return True

        return False

    for emoji in emotes:
        await msg.add_reaction(emoji)
    await msg.add_reaction('❌')

    try:
        await ctx.bot.wait_for('raw_reaction_add', check=check, timeout=timeout)
    except asyncio.TimeoutError:
        confirm = None

    try:
        if delete_after:
            await msg.delete()
    finally:
        return confirm


async def try_send_hook(guild, bot, hook, regular_ch, embed, content=None, log_logMismatch=True):
    hook_ok = False
    if hasattr(hook, 'channel_id'):
        hook_ok = regular_ch.id == hook.channel_id
    if hook and hook_ok:
        try:
            await hook.send(embed=embed, content=content)
        except:
            return await regular_ch.send(embed=embed, content=content)
    else:
        if not hook_ok:
            if log_logMismatch:
                warn = "⚠**Logging hook and channel id mismatch, please fix!**⚠\n" \
                       "Can probably be fiex by changing the hook's target channel.\n" \
                       f"Or `{bot_pfx(bot, regular_ch)}setup webhooks` if there's something else wrong.\n" \
                       f"Target channel has to be {regular_ch.mention}" \
                       f"(tip: run the command `{bot_pfx(bot, regular_ch)}sup cur`)"
                error_logger.error(f"**Logging hook and channel id mismatch, please fix!!! on: {guild} (id: "
                                   f"{guild.id})**")
                content = f"{'' if not content else content}\n\n{warn}"
        return await regular_ch.send(embed=embed, content=content)


async def dm_log_try_setup(bot):
    failed = False
    if bot.config['BOT_DM_LOG']['CAN_SEND'] == 0:
        try:
            g = bot.get_guild(bot.config['BOT_DM_LOG']['GUILD_ID'])
            if g:
                ch = bot.get_channel(bot.config['BOT_DM_LOG']['CHANNEL_ID'])
                if ch:
                    hooks = await ch.webhooks()
                    for h in hooks:
                        if h.name == f'{bot.user.name} dm log':
                            bot.config['BOT_DM_LOG']['HOOK'] = h
                            bot.config['BOT_DM_LOG']['CAN_SEND'] = 1
                            return True
                    hook = await ch.create_webhook(name=f'{bot.user.name} dm log',
                                                   reason="Logging webhook was missing or renamed")
                    bot.config['BOT_DM_LOG']['HOOK'] = hook
                    # set the webhooks pfp
                    url = str(bot.user.display_avatar.url).replace('.webp', '.png')
                    tf = f'w{str(int(datetime.datetime.utcnow().timestamp()))}w'
                    fnn = await saveFile(url, 'tmp', tf)  # copy from dutils because circular import
                    with open(fnn, 'rb') as fp:
                        await hook.edit(avatar=fp.read())
                    os.remove(fnn)
                    bot.config['BOT_DM_LOG']['CAN_SEND'] = 1
                    return True
                else:
                    failed = True
            else:
                failed = True
            if failed:
                bot.config['BOT_DM_LOG']['CAN_SEND'] = -1
                return False
        except:
            bot.config['BOT_DM_LOG']['CAN_SEND'] = -1
            return False
    elif bot.config['BOT_DM_LOG']['CAN_SEND'] == -1:
        return False
    else:  # == 1
        return True


def icon_url(user):
    return user.display_avatar.url if 'gif' in str(user.display_avatar.url).split('.')[-1] else str(
        user.display_avatar.with_format("png").url)


async def dm_log(bot, message: discord.Message):
    cnt = message.content
    if bot.config['BOT_DM_LOG']['HOOK'] == 0:
        print(f"DM WEBHOOK GONE? Dm by {message.author.id} | {message.content}")
        return
    try:
        descs = []
        txt = message.content
        if not txt: txt = "*there was no content*"
        while len(txt) > 0:
            descs.append(txt[:1024])
            txt = txt[1024:]
        a_title = str(message.author)
        ems = []
        i = 1
        for desc in descs:
            if len(descs) > 1:
                a_title += f' {i}/{len(descs)}'
                i += 1
            icon_url = message.author.display_avatar.url if 'gif' in str(message.author.display_avatar.url).split('.')[
                -1] else str(
                message.author.display_avatar.with_format("png").url)
            em = Embed(description=desc)
            em.set_author(name=a_title, icon_url=icon_url)
            em.set_thumbnail(url=icon_url)
            a_title = str(message.author)
            em.set_footer(text=f"{datetime.datetime.utcnow().strftime('%c')} | "
                               f'{message.author.id}')
            if message.attachments:
                val = ("\n".join(f'[{j}. {s.filename}]({s.url})'
                                 for j, s in enumerate(message.attachments, 1)))
                if len(val) > 1024:
                    val = (" ".join(f'[{j}]({s.url})' for j, s in enumerate(message.attachments, 1)))
                    if len(val) > 1024:
                        val = f'https://cdn.discordapp.com/attachments/{message.channel.id}/...\n'
                        rest = ("\n".join(f'{"/".join(s.url.split("/")[-2:])}'
                                          for j, s in enumerate(message.attachments, 1)))
                        val += rest
                        val += '\n\n**Combine all these into urls with `dmlu PASTE_HERE`**'
                em.add_field(name="Attachements", value=val)
            ems.append(em)
        for e in ems:
            await bot.config['BOT_DM_LOG']['HOOK'].send(embed=e)
    except:
        print(f'---{datetime.datetime.utcnow().strftime("%c")}---')
        print("exception in dm logging")
        traceback.print_exc()
        bot.config['BOT_DM_LOG']['HOOK'] = 0
        bot.config['BOT_DM_LOG']['CAN_SEND'] = 0


async def ban_function(ctx, user, reason="", removeMsgs=0, massbanning=False,
                       no_dm=False, softban=False, actually_resp=None,
                       author=None, guild=None, bot=None, respch=None):
    if ctx:
        respch = ctx
        author = ctx.author
        guild = ctx.guild
        bot = ctx.bot
    member = user
    if not member:
        if massbanning: return -1
        return await respch.send('Could not find this user in this server')
    if member:
        try:
            if massbanning:
                bot.banned_cuz_blacklist[f'{member.id}_{guild.id}'] = 2
            if not massbanning:
                bot.just_banned_by_bot[f'{member.id}_{guild.id}'] = 1
            # await member.ban(reason=reason, delete_message_days=removeMsgs)
            await guild.ban(member, reason=reason, delete_message_seconds=removeMsgs * 24 * 60 * 60)
            if softban:
                # await member.unban(reason='Softbanned')
                await guild.unban(member, reason='Softbanned')
            try:
                aa = isinstance(member, discord.Member)
                if not no_dm and not massbanning and isinstance(member, discord.Member):
                    await member.send(f'You have been {"banned" if not softban else "soft-banned"} '
                                      f'from the {str(guild)} '
                                      f'server {"" if not reason else f", reason: {reason}"}')
            except:
                pass
                # print(f"Member {'' if not member else member.id} disabled dms")
            return_msg = f'{"Banned" if not softban else "Soft-banned"} the user {member.mention} (id: {member.id})'
            if reason:
                return_msg += f" for reason: `{reason}`"

            if not massbanning:
                await respch.send(embed=Embed(description=return_msg, color=0xdd0000))
            if not massbanning:
                typ = "ban"
                if removeMsgs == 7: typ = "banish"
                if softban and removeMsgs == 0: typ = "softban"
                if softban and removeMsgs == 7: typ = "softbanish"
                act_id = await moderation_action(ctx, reason, typ, member, no_dm=no_dm, actually_resp=actually_resp)
                await post_mod_log_based_on_type(ctx, typ, act_id, offender=member,
                                                 reason=reason, actually_resp=actually_resp)
            if not ctx and massbanning:
                act_id = await moderation_action(None, reason, 'ban', member, no_dm=no_dm,
                                                 actually_resp=author,
                                                 guild=guild, bot=bot)
                await post_mod_log_based_on_type(None, 'ban', act_id, offender=member,
                                                 reason=reason,
                                                 actually_resp=author,
                                                 guild=guild, bot=bot)

            return member.id
        except discord.Forbidden:
            if massbanning:
                del bot.banned_cuz_blacklist[f'{member.id}_{member.guild.id}']
            if massbanning: return -100  # special return
            await respch.send('Could not ban user. Not enough permissions.')
    else:
        if massbanning: return -1
        return await respch.send('Could not find user.')


async def unmute_user_auto(member, guild, bot, no_dm=False, actually_resp=None, reason="Auto"):
    try:
        mute_role = discord.utils.get(guild.roles, id=bot.from_serversetup[guild.id]['muterole'])
        if mute_role not in guild.get_member(member.id).roles:
            return
        await member.remove_roles(mute_role, reason=f'{reason}|selfmute|{no_dm}')
        # try: done in listener
        #     muted = Reminderstbl.get(Reminderstbl.guild == guild.id, Reminderstbl.user_id == member.id)
        #     muted.delete_instance()
        # except:
        #     pass
        try:
            if not no_dm:
                await member.send(f'You have been unmuted on the {str(guild)} server.'
                                  f'{"" if not reason else f" Reason: **{reason}**"}')
        except:
            pass
        # act_id = await moderation_action(None, reason, "unmute", member, no_dm=no_dm,
        #                                  actually_resp=actually_resp, guild=guild, bot=bot)
        # await post_mod_log_based_on_type(None, "unmute", act_id, offender=member,
        #                                  reason=reason, actually_resp=actually_resp,
        #                                  guild=guild, bot=bot)
    except:
        # print(f'---{datetime.datetime.utcnow().strftime("%c")}---')
        # traceback.print_exc()
        error_logger.error(f"can not auto unmute {guild} {guild.id}\n{traceback.format_exc()}")


async def unmute_user(ctx, member, reason, no_dm=False, actually_resp=None):
    try:
        can_even_execute = True
        if ctx.guild.id in ctx.bot.from_serversetup:
            sup = ctx.bot.from_serversetup[ctx.guild.id]
            if not sup['muterole']: can_even_execute = False
        else:
            can_even_execute = False
        # if not can_even_execute: return ctx.send("Mute role not setup, can not complete unmute.")
        if not can_even_execute: return error_logger.error(f"Mute role not setup, can not "
                                                           f"complete unmute. {ctx.guild}, {ctx.jump_url}")
        mute_role = discord.utils.get(ctx.guild.roles, id=ctx.bot.from_serversetup[ctx.guild.id]['muterole'])
        if mute_role not in ctx.guild.get_member(member.id).roles:
            return await ctx.send("User is not muted")

        await member.remove_roles(mute_role, reason=f'{reason}|{no_dm}')
        # try: (now done in the listener)
        #     muted = Reminderstbl.get(Reminderstbl.guild == ctx.guild.id, Reminderstbl.user_id == member.id)
        #     muted.delete_instance()
        # except:
        #     pass
        await ctx.send(embed=Embed(description=f"{member.mention} has been unmuted.", color=0x76dfe3))
        try:
            if not no_dm:
                await member.send(f'You have been unmuted on the {str(ctx.guild)} server.'
                                  f'{"" if not reason else f" Reason: **{reason}**"}')
        except:
            pass
            # print(f"Member {'' if not member else member.id} disabled dms")
            # act_id = await moderation_action(ctx, reason, "unmute", member, no_dm=no_dm, actually_resp=actually_resp)
            # await post_mod_log_based_on_type(ctx, "unmute", act_id, offender=member,
            #                                  reason=reason, actually_resp=actually_resp)
    except discord.errors.Forbidden:
        await ctx.send("💢 I don't have permission to do this.")


async def mute_user(ctx, member, length, reason, no_dm=False, new_mute=False, batch=False,
                    guild=None, bot=None, author=None, fdbch=None, selfmute=False):
    """
    When ctx is missing, be sure to input the guild and bot and make.
    If ctx == None and you don't want the feedback, just turn on batch
    """
    if selfmute:
        reason = "[selfmute] " + reason
    if ctx:
        guild = ctx.guild
        bot = ctx.bot
        fdbch = ctx
        author = ctx.author
    can_even_execute = True
    if guild.id in bot.from_serversetup:
        sup = bot.from_serversetup[guild.id]
        if not sup['muterole']: can_even_execute = False
    else:
        can_even_execute = False
    if not can_even_execute:
        if not batch:
            return fdbch.send("Mute role not setup, can not complete mute.")
        else:
            return -1000
    mute_role = discord.utils.get(guild.roles, id=bot.from_serversetup[guild.id]['muterole'])
    if not new_mute:
        if mute_role in guild.get_member(member.id).roles:
            if not batch:
                return await fdbch.send(embed=Embed(description=f'{member.mention} is already muted', color=0x753c34))
            else:
                return -10
    unmute_time = None
    # thanks Luc#5653
    if length:
        units = {
            "d": 86400,
            "h": 3600,
            "m": 60,
            "s": 1
        }
        seconds = 0
        match = re.findall("([0-9]+[smhd])", length)  # Thanks to 3dshax
        if not match:
            # p = bot_pfx(bot, ctx.message)
            p = bot_pfx_by_gid(bot, guild.id)
            if not batch:
                return await fdbch.send(f"Could not parse mute length. Are you sure you're "
                                        f"giving it in the right format? Ex: `{p}mute @user 30m`, "
                                        f"or `{p}mute @user 1d4h3m2s reason here`, etc.")
            else:
                return -35

        try:
            for item in match:
                seconds += int(item[:-1]) * units[item[-1]]
            timestamp = datetime.datetime.utcnow()
            delta = datetime.timedelta(seconds=seconds)
        except OverflowError:
            if not batch:
                return await fdbch.send("**Overflow!** Mute time too long. Please input a shorter mute time.")
            else:
                return 9001
        if (seconds < 300) and selfmute:
            await fdbch.send("Selfmute time can not be less than 5 minutes!")
            return 0
        if (seconds > 60 * 60 * 24) and selfmute:
            await fdbch.send("Selfmute time can not be more than 24 hours!")
            return 0

        unmute_time = timestamp + delta

    try:
        bot.just_muted_by_bot[f'{member.id}_{member.guild.id}'] = 1
        await member.add_roles(mute_role, reason=reason)
        try:
            if not no_dm:
                await member.send(f'You have been muted on the {str(guild)} server '
                                  f'{"for " + length if length else "indefinitely "}'
                                  f' {"" if not reason else f"reason: {reason}"}')
        except:
            # print(f"Member {'' if not member else member.id} disabled dms")
            pass
    except discord.errors.Forbidden:
        del bot.just_muted_by_bot[f'{member.id}_{member.guild.id}']
        if not batch:
            return await fdbch.send("💢 I don't have permission to do this.")
        else:
            return -19
    new_reason = reason  # deleted this functionality to not spam db
    reminder = bot.get_cog('Reminders')
    if reminder is None:
        if not batch:
            return await fdbch.send('Can not load remidners cog! (Weird error)')
        else:
            return -989
    updating_mute = True
    try:
        mute = Reminderstbl.get(Reminderstbl.user_id == member.id, Reminderstbl.guild == guild.id,
                                Reminderstbl.meta.startswith('mute'))
        d = 0
    except:
        updating_mute = False
    tim = await reminder.create_timer(
        expires_on=unmute_time if length else datetime.datetime.max,
        meta='mute_nodm' if no_dm else 'mute',
        gid=guild.id,
        reason=new_reason,
        uid=member.id,
        len_str='indefinitely ' if not length else length,
        author_id=author.id,
        should_update=updating_mute
    )
    if not batch:
        if not selfmute:
            await fdbch.send(embed=Embed(
                description=f"{member.mention} is now muted from text channels{' for ' + length if length else ''}.",
                color=0x6785da))
        if selfmute:
            await fdbch.send(embed=Embed(
                description=f"{member.mention} muted themselves {' for ' + length if length else ''}.",
                color=0x7fc0d4))
        if ctx:
            act_id = await moderation_action(ctx, new_reason, "mute", member, no_dm=no_dm, actually_resp=author)
            await post_mod_log_based_on_type(ctx, "mute", act_id,
                                             mute_time_str='indefinitely' if not length else length,
                                             offender=member, reason=new_reason, actually_resp=author)
    if not ctx and batch:
        act_id = await moderation_action(None, new_reason, 'mute', member, no_dm=no_dm,
                                         actually_resp=author,
                                         guild=guild, bot=bot)
        await post_mod_log_based_on_type(None, 'mute', act_id, offender=member,
                                         reason=new_reason,
                                         mute_time_str='indefinitely' if not length else length,
                                         actually_resp=author,
                                         guild=guild, bot=bot)
    return 10
    # dataIOa.save_json(self.modfilePath, modData)
    # await dutils.mod_log(f"Mod log: Mute", f"**offender:** {str(member)} ({member.id})\n"
    #                                       f"**Reason:** {reason}\n"
    #                                       f"**Responsible:** {str(ctx.author)} ({ctx.author.id})",
    #                     colorr=0x33d8f0, author=ctx.author)


async def moderation_action(ctx, reason, action_type, offender, no_dm=False,
                            actually_resp=None, guild=None, bot=None):
    """
    :param ctx: ctx
    :param reason: reason
    :param action_type: mute, warn, ban, blacklist
    :param offender: offender member
    :param no_dm: did the member recieve a dm of the action
    :param actually_resp: in case the responsible isn't the one in the ctx (has to be filled if ctx is None)
    :param guild: has to be filled if ctx is None
    :param bot: has to be filled if ctx is None
    :return: insert id or None if fails
    """
    chan = 0
    jump = "(auto)"
    if ctx:
        guild = ctx.guild
        bot = ctx.bot
        author = ctx.author
        p = bot_pfx(bot, ctx.message)
        chan = ctx.channel.id
        jump = ctx.message.jump_url
    try:
        disp_n = "(left server)"
        if offender and hasattr(offender, 'id'):
            disp_n = offender.display_name
            offender = offender.id
        resp = None
        if actually_resp:
            resp = actually_resp
        else:
            resp = ctx.author
        ins_id = Actions.insert(guild=guild.id, reason=reason, type=action_type, channel=chan,
                                jump_url=jump, responsible=resp.id,
                                offender=offender, user_display_name=disp_n, no_dm=no_dm).execute()
        case_id = Actions.select().where(Actions.guild == guild.id).count()
        Actions.update(case_id_on_g=case_id).where(Actions.id == ins_id).execute()
        return case_id
    except:
        error_logger.error(f"Failed to insert mod action: {jump}")
        return None


async def post_mod_log_based_on_type(ctx, log_type, act_id, mute_time_str="",
                                     offender=None, reason=None, warn_number=1,
                                     actually_resp=None, guild=None, bot=None):
    # Make CTX None if it doesnt exist, but do make guild and bot and actually_resp are something
    if ctx:
        guild = ctx.guild
        bot = ctx.bot
        author = ctx.author
        p = bot_pfx(bot, ctx.message)
    else:
        p = bot_pfx_by_gid(bot, guild.id)

    em = Embed()
    responsb = None
    le_none = "*No reason provided.\n" \
              "Can still be supplied with:\n" \
              f"`{p}case {act_id} reason here`*"
    if actually_resp:
        responsb = actually_resp
    else:
        responsb = ctx.author
    if not reason: reason = le_none

    em.add_field(name='Responsible', value=f'{responsb.mention}\n{responsb}', inline=True)
    off_left_id = -1  # -1 means that offender exists on the server
    if offender and not hasattr(offender, 'id'):
        off_left_id = offender

    if offender and off_left_id == -1:
        em.add_field(name='Offender', value=f'{offender.mention}\n{offender}\n{offender.id}', inline=True)
    if offender and off_left_id != -1:
        em.add_field(name='Offender', value=f'{off_left_id}\n(left server)', inline=True)

    if log_type == 'blacklist':
        em.add_field(name='Reason', value=f'{le_none}\n**Ofenders:**\n{reason}', inline=True if offender else False)
    if log_type == 'whitelist':
        em.add_field(name='Reason', value=f'{le_none}\n**Command:**\n{reason.split("|")[0]}'
                                          f'\n**Result:**\n{reason.split("|")[-1]}', inline=True if offender else False)
    # these above have to be the ones in the bottom array
    if log_type not in ['blacklist', 'whitelist']:
        em.add_field(name='Reason', value=reason, inline=True if offender else False)

    try:
        cmdi = f"[Cmd invoke happened here]({ctx.message.jump_url}) in {ctx.channel.mention}"
        em.add_field(name="Extra info", value=cmdi, inline=True if offender else False)
    except:
        pass

    title = ""
    if log_type == 'mute':
        title = "User muted indefinitely" if mute_time_str == 'indefinitely' else f'User muted for {mute_time_str}'
        em.colour = 0xbf5b30

    if log_type == 'Right click mute':
        title = "User right click muted"
        em.colour = 0xbf5b30

    if 'ban' in log_type and log_type != 'unban':
        title = log_type.capitalize()
        em.colour = 0xe62d10

    if log_type == 'unban':
        title = "User unbanned"
        em.colour = 0x45ed9c

    if log_type == 'blacklist':
        title = "Blacklist"
        em.colour = 0x050100

    if log_type == 'whitelist':
        title = "whitelist"
        em.colour = 0xfcf7f7

    if log_type == 'warn':
        tim = 'times already' if warn_number > 1 else 'time'
        title = f'User warned ({warn_number} {tim})'
        em.colour = 0xfa8507

    if log_type == 'unmute':
        title = f"User unmuted"
        em.colour = 0x62f07f

    if log_type == 'kick':
        title = f"User kicked"
        em.colour = 0xe1717d

    if log_type == 'clearwarn':
        title = f"Warning cleared for offender"
        em.colour = 0x398de4

    if log_type == 'massmute':
        title = "Users muted indefinitely" if mute_time_str == 'indefinitely' else f'Users muted for {mute_time_str}'
        em.colour = 0x9e4b28

    # em.set_thumbnail(url=get_icon_url_for_member(ctx.author))
    if offender:
        em.set_author(name=title, icon_url=get_icon_url_for_member(offender))
    else:
        em.title = title
    em.set_footer(text=f"{datetime.datetime.utcnow().strftime('%c')} | "
                       f'Case id: {act_id}')
    now = datetime.datetime.utcnow()
    if reason.strip() not in ['[selfmute]']:
        await log(bot, this_embed=em, this_hook_type='modlog', guild=guild)
    if not bot.from_serversetup:
        bot.from_serversetup = await SSManager.get_setup_formatted(bot)
    if guild.id not in bot.from_serversetup: return

    sup = bot.from_serversetup[guild.id]
    if f'modlog' not in sup or not sup[f'modlog']: return
    if f'hook_modlog' not in sup or not sup[f'hook_modlog']: return
    chan = sup['modlog']
    if chan:
        Actions.update(logged_after=now, logged_in_ch=chan.id
                       ).where(Actions.case_id_on_g == act_id,
                               Actions.guild == guild.id).execute()


async def log(bot, title=None, txt=None, author=None,
              colorr=0x222222, imageUrl='', guild=None, content=None,
              this_embed=None, this_content=None,
              this_hook_type=None):
    """
    :param title:
    :param txt:
    :param author:
    :param colorr:
    :param imageUrl:
    :param guild:
    :param content:
    :param this_embed:
    :param this_content:
    :param this_hook_type: this_hook_type: reg | leavejoin | modlog
    :param bot:
    :return:
    """
    try:
        hook_typ = 'reg'
        if this_hook_type: hook_typ = this_hook_type
        if not bot.from_serversetup:
            bot.from_serversetup = await SSManager.get_setup_formatted(bot)
        if guild.id not in bot.from_serversetup: return
        sup = bot.from_serversetup[guild.id]

        if f'{hook_typ}' not in sup or not sup[f'{hook_typ}']: return
        if f'hook_{hook_typ}' not in sup or not sup[f'hook_{hook_typ}']: return
        if not this_content and not this_embed:
            desc = []
            while len(txt) > 0:
                desc.append(txt[:2000])
                txt = txt[2000:]
            i = 0
            for txt in desc:
                em = discord.Embed(description=txt, color=colorr)
                if author:
                    iconn_url = author.display_avatar.url if 'gif' in str(author.display_avatar.url).split('.')[-1] \
                        else str(author.display_avatar.with_format("png").url)
                    em.set_author(name=f"{title}", icon_url=iconn_url)
                em.set_footer(text=f"{datetime.datetime.utcnow().strftime('%c')}")
                if imageUrl:
                    try:
                        em.set_thumbnail(url=imageUrl)
                    except:
                        pass
                if title and not author:
                    em.title = title
                cnt = None
                if i == 0 and content:
                    cnt = content
                    i += 1

                return await try_send_hook(guild, bot, hook=sup[f'hook_{hook_typ}'],
                                           regular_ch=sup[hook_typ], embed=em, content=cnt)
        else:
            return await try_send_hook(guild, bot,
                                       hook=sup[f'hook_{hook_typ}'],
                                       regular_ch=sup[hook_typ], embed=this_embed,
                                       content=this_content)

    except:
        # print(f'---{datetime.datetime.utcnow().strftime("%c")}---')
        # traceback.print_exc()
        error_logger.error(f"Something went wrong when logging\n{traceback.format_exc()}")


async def ban_from_bot(bot, offender, meta, gid, ch_to_reply_at=None, arl=0):
    if offender.id == bot.config['OWNER_ID']: return
    # print(meta)
    bot.banlist[offender.id] = meta
    try:
        bb = BotBanlist.get(BotBlacklist.user == offender.id)
        bb.meta = meta
        bb.when = datetime.datetime.utcnow()
        bb.guild = gid
        bb.save()
    except:
        BotBanlist.insert(user=offender.id, guild=gid, meta=meta).execute()
    if ch_to_reply_at:
        if arl < 2:
            await ch_to_reply_at.send(f'💢 💢 💢 {offender.mention} you have been banned from the bot!')


async def blacklist_from_bot(bot, offender, meta, gid, ch_to_reply_at=None, arl=0):
    if offender.id == bot.config['OWNER_ID']: return
    # print(meta)
    bot.blacklist[offender.id] = meta
    try:
        bb = BotBlacklist.get(BotBlacklist.user == offender.id)
        bb.meta = meta
        bb.when = datetime.datetime.utcnow()
        bb.guild = gid
        bb.save()
    except:
        BotBlacklist.insert(user=offender.id, guild=gid, meta=meta).execute()
    if arl < 2 and ch_to_reply_at:
        await ch_to_reply_at.send(
            f'💢 {offender.mention} you have been blacklisted from the bot '
            f'for spamming. You may remove yourself from the blacklist '
            f'once in a certain period. '
            f'To do that you can use `{bot_pfx_by_gid(bot, gid)}unblacklistme`')


def get_icon_url_for_member(member):
    avatar_url = member.display_avatar.url
    if avatar_url and 'gif' in avatar_url.split('.')[-1]:
        return avatar_url
    elif member.display_avatar:
        return member.display_avatar.with_format("png").url
    else:
        return member.default_avatar.url


async def saveFiles(links, savePath='tmp', fName=''):
    # https://cdn.discordapp.com/attachments/583817473334312961/605911311401877533/texture.png
    fileNames = []
    for ll in links:
        try:
            urll = ll.url
        except:
            urll = ll
        fileName = f'{savePath}/' + str(datetime.datetime.utcnow().timestamp()).replace('.', '') \
                   + '.' + str(urll).split('.')[-1] \
            if not fName else f'{savePath}/{fName}_{str(datetime.datetime.utcnow().timestamp()).replace(".", "")}' + \
                              '.' + str(urll).split('.')[-1]
        fileNames.append(fileName)
        async with aiohttp.ClientSession() as session:
            async with session.get(urll) as r:
                with open(fileName, 'wb') as fd:
                    async for data in r.content.iter_chunked(1024):
                        fd.write(data)
    return fileNames


async def lock_channels(ctx, channels):
    try:
        all_ch = False
        silent = False
        if "silent" in channels.lower().strip():
            silent = True

        if "all" in channels.lower().strip():
            all_ch = True
            user = ctx.guild.get_member(ctx.bot.user.id)
            channels = [channel for channel in ctx.guild.text_channels if
                        channel.permissions_for(user).manage_roles]
        elif len(ctx.message.channel_mentions) == 0:
            channels = [ctx.channel]
        elif len(ctx.message.channel_mentions) == 0:
            channels = [ctx.channel]
        else:
            channels = ctx.message.channel_mentions
        perma_locked_channels = []
        m = None
        if all_ch:
            m = await ctx.send(f"Locking all channels{'' if not silent else ' silently'}")
        for c in channels:
            ow = ctx.guild.default_role
            overwrites_everyone = c.overwrites_for(ow)
            if all_ch and overwrites_everyone.send_messages is False:
                perma_locked_channels.append(str(c.id))
                continue
            elif overwrites_everyone.send_messages is False:
                await ctx.send(f"🔒 {c.mention} is already locked down. Use `.unlock` to unlock.")
                continue
            overwrites_everyone.send_messages = False
            await c.set_permissions(ow, overwrite=overwrites_everyone)
            if not silent:
                await c.send("🔒 Channel locked.")

        if perma_locked_channels:
            try:
                g = ArGuild.get(ArGuild.id == ctx.guild.id)
                g.perma_locked_channels = ' '.join(perma_locked_channels)
            except:
                ArGuild.insert(id=ctx.guild.id).execute()
        if m: await m.delete()
        if all_ch:
            await ctx.send('Done.')
    except discord.errors.Forbidden:
        await ctx.send("💢 I don't have permission to do this.")


async def unlock_channels(ctx, channels):
    try:
        all_ch = False
        silent = False
        if "silent" in channels.lower().strip():
            silent = True
        if "all" in channels.lower().strip():
            all_ch = True
            user = ctx.guild.get_member(ctx.bot.user.id)
            channels = [channel for channel in ctx.guild.text_channels if
                        channel.permissions_for(user).manage_roles]
        elif len(ctx.message.channel_mentions) == 0:
            channels = [ctx.channel]
        else:
            channels = ctx.message.channel_mentions
        perma_locked_channels = []
        if all_ch:
            try:
                g = ArGuild.get(ArGuild.id == ctx.guild.id)
                perma_locked_channels = g.perma_locked_channels.split()
            except:
                if all_ch: return await ctx.send(
                    'Can not use `unlock all` without `lock all` '
                    'being used at least once before on the server.')
        m = None
        if all_ch:
            m = await ctx.send(f"Unlocking all channels{'' if not silent else ' silently'}")
        for c in channels:
            ow = ctx.guild.default_role
            overwrites_everyone = c.overwrites_for(ow)
            if all_ch and str(c.id) in perma_locked_channels:
                continue
            elif overwrites_everyone.send_messages is None:
                await ctx.send(f"🔓 {c.mention} is already unlocked.")
                continue
            overwrites_everyone.send_messages = None
            await c.set_permissions(ow, overwrite=overwrites_everyone)
            if not silent:
                await c.send("🔓 Channel unlocked.")
        if m: await m.delete()
        if all_ch:
            return await ctx.send('Done.')

    except discord.errors.Forbidden:
        await ctx.send("💢 I don't have permission to do this.")


async def punish_based_on_arl(arl, message, bot, mentions=False):
    extra_rsn = ' mass mention' if mentions else ' spam'
    rsn = f"Level {arl} raid protection:\n**{extra_rsn}**"
    if arl == 2:
        # async def mute_user(ctx, member, length, reason, no_dm=False, new_mute=False, batch=False,
        #                     guild=None, bot=None, author=None, fdbch=None):
        if message.guild:
            return await mute_user(None, message.author, '', rsn,
                                   no_dm=True, batch=True, guild=message.guild, bot=bot,
                                   author=bot.user)
    if arl == 3:
        if len(message.author.roles) == 1:  # if member has no roles
            await ban_function(None, message.author, rsn,
                               removeMsgs=1, no_dm=True,
                               author=bot.user, guild=message.guild, bot=bot, massbanning=True)
        else:
            m = message.guild.get_member(message.author.id)
            # print(str(m))
            if m:
                try:
                    await message.author.kick(reason=rsn)
                    act_id = await moderation_action(None, rsn, 'kick', message.author, no_dm=True,
                                                     actually_resp=bot.user,
                                                     guild=message.guild, bot=bot)
                    await post_mod_log_based_on_type(None, 'kick', act_id, offender=message.author,
                                                     reason=rsn,
                                                     actually_resp=bot.user,
                                                     guild=message.guild, bot=bot)
                except:
                    pass


async def try_get_member(ctx, user):
    member = None
    if not user: return member

    if ctx.message.mentions:
        member = ctx.message.mentions[0]
    elif user and user.isdigit():
        member = ctx.guild.get_member(int(user))
    else:
        member = discord.utils.get(ctx.guild.members, name=user)
    return member


async def add_tmp_emote(bot, ctx, emoteName, picUrl, ext, servID=0, additForGood=False):
    loopOver = bot.emote_servers_tmp if not additForGood else bot.emote_servers_perm
    if servID != 0:
        loopOver = [servID]
    err = ""
    for servId in loopOver:
        serv = bot.get_guild(int(servId))
        if not serv: continue
        nonAni = [e for e in serv.emojis if not e.animated]
        if ext != 'gif':
            if len(nonAni) == serv.emoji_limit:
                if servID and additForGood:
                    return "", f"**{str(serv)}** is packed on normal emotes"
                print(f'EMOTE LOG {str(serv)} - {servId}: packed on normal emotes')
                continue
        else:
            if len(serv.emojis) - len(nonAni) == serv.emoji_limit:
                if servID and additForGood:
                    return "", f"**{str(serv)}** is packed on animated emotes"
                print(f'EMOTE LOG {str(serv)} - {servId}: packed on animated emotes')
                continue

        fn = await saveFiles([picUrl], 'tmp', emoteName)
        fnn = str(fn).split('/')[-1].split('.')[-2] if not additForGood else emoteName
        size = os.stat(fn[0]).st_size
        if size < 256000:
            with open(fn[0], 'rb') as fp:
                emoji = await serv.create_custom_emoji(name=fnn[:32], image=fp.read())
        else:
            nn = fnn[:32].replace('@', '@\u200b')
            os.remove(fn[0])
            return "", f'File size for **{nn}** is too big after saving the tmp file. ' \
                       f'Please give me a smaller or more compressed ' \
                       'vesrion of this file.'
        os.remove(fn[0])
        return str(emoji), err

    # if additForGood: await ctx.send('Could not add emote for some reason')
    return False, err  # no appropriate servers found


def left_member_top_role_is_compared_to_right(user1, user2):
    # owner is higher by default regardless of roles
    if user1.id == user1.guild.owner_id: return "higher"
    if user2.id == user1.guild.owner_id: return "lower"
    role1 = user1.top_role
    role2 = user2.top_role
    if role1 > role2: return "higher"
    if role1 < role2: return "lower"
    return "same"


async def can_execute_based_on_top_role_height(ctx, cmd, user1, user2, bot_test=False, silent=False, can_be_same=False):
    if isinstance(user2, discord.Member):
        h = left_member_top_role_is_compared_to_right(user1, user2)
        allowed = ["higher"]
        if can_be_same: allowed = ["higher", "same"]
        if h not in allowed:
            if not silent:
                await ctx.send(f"Can not {cmd} since {'your' if not bot_test else 'my'} top role is"
                               f" {'**the same** as' if h == 'same' else '**lower** than'} {user2}")
            return False
    return True


async def try_to_react(msg, reactionArr):
    for e in reactionArr:
        try:
            await msg.add_reaction(e)
        except:
            return False, e
    return True, ""


async def try_if_role_exists(guild, roleIdOrName):
    role = None
    try:
        if roleIdOrName.isdigit():
            role = discord.utils.get(guild.roles, id=int(roleIdOrName))
        if not role:
            role = discord.utils.get(guild.roles, name=str(roleIdOrName))
            if not role:
                raise
    except:
        return False, roleIdOrName, ''
    return True, "", role
