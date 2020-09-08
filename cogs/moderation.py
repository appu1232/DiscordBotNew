import asyncio
import time

import discord
from discord.ext import commands
from discord import Member, Embed, File, utils
import os
import traceback

from utils.SimplePaginator import SimplePaginator
from utils.dataIOa import dataIOa
import utils.checks as checks
import utils.discordUtils as dutils
import utils.timeStuff as tutils
import datetime
from columnar import columnar
from operator import itemgetter
from models.moderation import (Mutes, Actions, Blacklist, ModManager)


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.max_concurrency(1, commands.BucketType.channel)
    @commands.check(checks.ban_members_check)
    @commands.command(aliases=['prune'])
    async def purge(self, ctx, count: int, *users: discord.Member):
        """Clears a given number of messages or until the given message id.

        `[p]purge n` - purges the last n messages. Ex: .purge 100
        `[p]purge n @user` - purges all by @user in the last n messages. Ex: .purge 10 @kiki
        `[p]purge n @user1 @user2 @user3` - same as above but for more users
        `[p]purge <message_id>` - purges all up until specified msg. Ex: .purge 543075155458348436"""
        try:
            up_to = await ctx.channel.fetch_message(count)
        except discord.errors.NotFound:
            up_to = None
        if not up_to and count > 100:
            wait = await ctx.send(f"You are about to purge {count}. "
                                  f"Are you sure you want to purge these many messages? (y/n)")

            def check(m):
                return (m.content.lower() == 'y' or m.content.lower() == 'n') and \
                       m.author == ctx.author and m.channel == ctx.channel

            try:
                reply = await self.bot.wait_for("message", check=check, timeout=10)
            except asyncio.TimeoutError:
                return await ctx.send("Cancelled purge.")
            if not reply or reply.content.lower().strip() == 'n':
                return await ctx.send("Cancelled purge.")
            else:
                await wait.delete()
                await ctx.message.delete()
        try:
            if up_to:
                deleted = await ctx.channel.purge(limit=None, after=up_to,
                                                  check=lambda message: message.author in users if users else True)
                await up_to.delete()
            else:
                deleted = await ctx.channel.purge(limit=count + 1,
                                                  check=lambda message: message.author in users if users else True)
            # print(f'{datetime.datetime.now().strftime("%c")} ({ctx.guild.id} | {str(ctx.guild)}) MOD LOG (purge): '
            #       f'{str(ctx.author)} ({ctx.author.id}) purged {len(deleted)} '
            #       f'messages in {str(ctx.channel)} ({ctx.channel.id})')
            await ctx.send(f"Purged **{len(deleted) - 1}** messages", delete_after=5)
        except discord.HTTPException:
            await ctx.send("Something went wrong! Could not purge.")

    @commands.check(checks.manage_channels_check)
    @commands.command()
    async def case(self, ctx, case_id: int, *, reason):
        """Supply a reason to a claim witht out one"""
        pass

    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.check(checks.manage_channels_check)
    @commands.command(aliases=["listcase", "lsc", 'showcase', 'showcases'])
    async def listcases(self, ctx, case_id: int = 0, limit=10, *, types: str = ""):
        """List case(s), see help to see command usage
        Use this command to see a case or multiple caes

        Use case examples:

        **I want to see a list of recent caes**
        `[p]lsc` (will simply show the last 10 cases)
        `[p]lsc 0 30` <- use this if you want to change the limt
        `[p]lsc -1 30` <- use `-1` there to view **any** querry reversed

        **I want to see one specific case by id**
        `[p]lsc case_id`

        **I want to see 40 cases before/after a certain date**
        snyax: (YEAR, MONTH, DAY, HOUR, MINUTE, SECOND) *all be filled out!!*
        `[p]lsc 0 40 before=(2020, 10, 8, 23, 50, 0)`
        `[p]lsc 0 40 after=(2020, 5, 5, 0, 0, 0) mute`

        **I want to see only one or more types of case**
        `[p]lsc 0 40 mute` (Will show up to 40 last mutes)
        `[p]lsc 0 10 softban banish` (shows up to 10 last softbans or banishes)

        **What are the possible case types anyway?**
        `*ban*` - any ban type case
        `ban` - regular ban
        `banish` - ban but with 7 days purged messages
        `softban` - ban, but unban right away
        `softbanish` - banish + softban (7 days messages rip)

        `mute` - mute action
        `warn` - warn action
        `blacklist` - blacklisted some users
        """
        if case_id == 0 and limit == 20 and not types:
            await ctx.send("TODO: Display all")

    @commands.check(checks.manage_messages_check)
    @commands.command()
    async def mute(self, ctx, user: discord.Member, length="", *, reason=""):
        """Mutes a user. Please check usage with .help mute

        Supply a #d#h#m#s for a timed mute. Examples:
        `[p]mute @user` - will mute the user indefinitely
        `[p]mute USER_ID` - can also use id instead of mention
        `[p]mute @user 2h30m Optional reason goes here`
        `[p]mute @user 10d Muted for ten days for that and this`"""
        can_even_execute = True
        if ctx.guild.id in ctx.bot.from_serversetup:
            sup = ctx.bot.from_serversetup[ctx.guild.id]
            if not sup['muterole']: can_even_execute = False
        else:
            can_even_execute = False
        if not can_even_execute: return await ctx.send(f"Mute role not setup. "
                                                       f"Use `{ctx.bot.config['BOT_PREFIX']}setup muterolenew <role>`")

        await dutils.mute_user(ctx, user, length, reason)

    @commands.check(checks.manage_messages_check)
    @commands.command(hidden=True)
    async def smute(self, ctx, user: discord.Member, length="", *, reason=""):
        """Mutes a user. Check usage with .help smute (no dm)

        Same as mute, but won't dm the muted user

        Supply a #d#h#m#s for a timed mute. Examples:
        `[p]smute @user` - will mute the user indefinitely
        `[p]smute USER_ID` - can also use id instead of mention
        `[p]smute @user 2h30m Optional reason goes here`
        `[p]smute @user 10d Muted for ten days for that and this`"""
        can_even_execute = True
        if ctx.guild.id in ctx.bot.from_serversetup:
            sup = ctx.bot.from_serversetup[ctx.guild.id]
            if not sup['muterole']: can_even_execute = False
        else:
            can_even_execute = False
        if not can_even_execute: return await ctx.send(f"Mute role not setup. "
                                                       f"Use `{ctx.bot.config['BOT_PREFIX']}setup muterolenew <role>`")

        await dutils.mute_user(ctx, user, length, reason, no_dm=True)

    @commands.check(checks.ban_members_check)
    @commands.command()
    async def ban(self, ctx, user: discord.Member, *, reason=""):
        """Ban a user with an optional reason. Prefix with `s` for "no dm"

        Tip:

        **Every ban/banish/softban/softbanish command (except massban)
        has another copy of it but with a `s` prefix**
        For example: `[p]sban @user` will ban them but
        will not dm them that they were banned.

        Ban = Delete no messages
        Banish = Delete 7 days of messages
        Softban = Ban but unban right away

        `[p]ban @user`
        `[p]ban USER_ID`
        `[p]ban USER_ID optional reason goes here here`"""
        await dutils.banFunction(ctx, user, reason)

    @commands.check(checks.ban_members_check)
    @commands.command(hidden=True)
    async def sban(self, ctx, user: discord.Member, *, reason=""):
        """Ban a user with an optionally supplied reason. **(won't dm them)**

        `[p]sban @user`
        `[p]sban USER_ID`
        `[p]sban USER_ID optional reason goes here here`"""
        await dutils.banFunction(ctx, user, reason, no_dm=True)

    @commands.check(checks.ban_members_check)
    @commands.command()
    async def banish(self, ctx, user: discord.Member, *, reason=""):
        """Same as ban but also deletes message history (7 days)

        `[p]banish @user`
        `[p]banish USER_ID`
        `[p]banish USER_ID optional reason goes here here`"""
        await dutils.banFunction(ctx, user, reason, removeMsgs=7)

    @commands.check(checks.ban_members_check)
    @commands.command(hidden=True)
    async def sbanish(self, ctx, user: discord.Member, *, reason=""):
        """Same as ban but also deletes message history (7 days) **(no dm)**

        `[p]sbanish @user`
        `[p]sbanish USER_ID`
        `[p]sbanish USER_ID optional reason goes here here`"""
        await dutils.banFunction(ctx, user, reason, removeMsgs=7, no_dm=True)

    @commands.check(checks.ban_members_check)
    @commands.command()
    async def softban(self, ctx, user: discord.Member, *, reason=""):
        """Ban, but unban right away

        `[p]softban @user`
        `[p]softban USER_ID`
        `[p]softban USER_ID optional reason goes here here`"""
        await dutils.banFunction(ctx, user, reason, softban=True)

    @commands.check(checks.ban_members_check)
    @commands.command(hidden=True)
    async def ssoftban(self, ctx, user: discord.Member, *, reason=""):
        """Ban, but unban right away (won't dm them)

        `[p]ssoftban @user`
        `[p]ssoftban USER_ID`
        `[p]ssoftban USER_ID optional reason goes here here`"""
        await dutils.banFunction(ctx, user, reason, softban=True, no_dm=True)

    @commands.check(checks.ban_members_check)
    @commands.command()
    async def softbanish(self, ctx, user: discord.Member, *, reason=""):
        """Ban, but unban right away also deletes message history (7 days)

        `[p]softbanish @user`
        `[p]softbanish USER_ID`
        `[p]softbanish USER_ID optional reason goes here here`"""
        await dutils.banFunction(ctx, user, reason, removeMsgs=7, softban=True)

    @commands.check(checks.ban_members_check)
    @commands.command(hidden=True)
    async def ssoftbanish(self, ctx, user: discord.Member, *, reason=""):
        """Ban, but unban right away also dels msg history (7d) **(no dm)**

        `[p]ssoftbanish @user`
        `[p]ssoftbanish USER_ID`
        `[p]ssoftbanish USER_ID optional reason goes here here`"""
        await dutils.banFunction(ctx, user, reason, removeMsgs=7, softban=True, no_dm=True)

    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.check(checks.ban_members_check)
    @commands.command()
    async def massban(self, ctx, delete_messages_days: int, *users: discord.Member):
        """Ban multiple users at once (no dm by default)

        **delete_messages_days** => Has to be 0 or more and 7 or less

        `[p]multiple 0 @user1 @user2 @user3` ...
        `[p]ban 7 USER_ID1 USER_ID2 USER_ID3 USER_ID4` ...

        ⚠If you got the invalid arguments error. Check the ids or user names/pings.
        Some are wrong.

        You can use `[p]massbantest <SAME_ARGUMENTS_AS_YOU_JUST_USED>`
        To test which of these users/ids/names/pings is wrong."""
        if len(users) == 1: return await ctx.send("Why would you *massban* only 1 user? Aborting.")
        if len(users) > 50: return await ctx.send("Can mass ban up to max 50 users at once.")
        if delete_messages_days > 7 or delete_messages_days < 0: return await ctx.send("**delete_messages_days**"
                                                                                       " has to be"
                                                                                       " 0 or more and 7 or less. Fix "
                                                                                       "that first...")
        users = list(set(users))  # remove dupes
        m = await ctx.send("Massbanning...")
        rets = []
        for user in users:
            rets.append(await dutils.banFunction(ctx, user, removeMsgs=delete_messages_days,
                                                 massbanning=True, no_dm=True, reason="massban"))
        orig_msg = f"Massban complete! Banned **{len([r for r in rets if r])}** users"
        ret_msg = orig_msg
        for i in range(len(rets)):
            if rets[i] < 0:
                if rets[i] == -1: ret_msg += f"\n**F1:** {users[i].id}"
                if rets[i] == -100: ret_msg += f"\n**F2:** {users[i].id}"
            else:
                pass

        await m.delete()
        if ret_msg != orig_msg:
            await ctx.send("**F1** means that the user couldn't be found.\n"
                           "**F2** means that I couldn't ban the user because not enough permissions")
        await ctx.send(embed=Embed(description=ret_msg))
        act_id = await dutils.moderation_action(ctx, "", "massban", None)
        await dutils.post_mod_log_based_on_type(ctx, 'massban', act_id)

    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.check(checks.ban_members_check)
    @commands.command()
    async def massbantest(self, ctx, delete_messages_days: int, *users):
        """Test if massban would work with these arguments"""
        if delete_messages_days > 7 or delete_messages_days < 0: return await ctx.send("**delete_messages_days**"
                                                                                       " has to be"
                                                                                       " 0 or more and 7 or less. Fix "
                                                                                       "that first...")
        wrong = ""
        for _u in users:
            try:
                if _u[:3] == "<@!" and _u[-1] == ">":
                    u = ctx.guild.get_member(int(_u[3:-1]))
                else:
                    u = ctx.guild.get_member(int(_u))
                if not u: wrong += (_u + '\n')
            except:
                u = discord.utils.get(ctx.guild.members, name=_u)
                if not u: wrong += (_u + '\n')
        wrong = wrong.replace('@', '@\u200b')

        if not wrong:
            await ctx.send("✅ Arguments are ok, this should work")
        else:
            await ctx.send("❌ Displaying wrong/bad arguments:\n\n" + wrong)

    async def if_you_need_loop(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                print("Code here")
            except:
                pass
            await asyncio.sleep(10)  # sleep here

    @commands.check(checks.ban_members_check)
    @commands.command()
    async def blacklist(self, ctx, *user_ids: int):
        """Blacklist a user or users by id"""
        user_ids = list(set(user_ids))  # remove dupes
        if len(user_ids) > 90: return await ctx.send("Can only blacklist up to 90 at once")
        data = [{'guild': ctx.guild.id, 'user_id': uid} for uid in user_ids]
        Blacklist.insert_many(data).execute()
        self.bot.moderation_blacklist = ModManager.return_blacklist_lists()
        await ctx.send("Done.")
        bs = ', '.join([str(u) for u in user_ids])
        act_id = await dutils.moderation_action(ctx, "", "blacklist", bs)
        await dutils.post_mod_log_based_on_type(ctx, 'blacklist', act_id, reason=bs, )

    @commands.check(checks.manage_messages_check)
    @commands.command()
    async def warn(self, ctx, user: discord.Member, *, reason):
        """Warn a user with a necessary supplied reason.

         `[p]warn @user Reason goes here` (reason has to be supplied)
         `[p]warn user_id Reason goes here`"""
        if reason == '': return await ctx.send('Warn failed, please supply '
                                               'a reason for the warn (`.warn @user '
                                               'reason goes here`)')
        act_id = await dutils.moderation_action(ctx, reason, 'warn', user)
        num_warns = Actions.select().where(Actions.type == 'warn',
                                           Actions.guild == ctx.guild.id,
                                           Actions.offender == user.id).count()
        await dutils.post_mod_log_based_on_type(ctx, 'warn', act_id, offender=user,
                                                reason=reason, warn_number=num_warns)
        await ctx.send(content=f'**{user.mention} has been warned, reason:**',
                       embed=Embed(description=reason).set_footer(
                           text=f'Number of warnings: {num_warns}'))
        try:
            await user.send(f'You have been warned on the {str(ctx.guild)} '
                            f'server, reason: {reason}')
        except:
            print(f"Member {'' if not user else user.id} disabled dms")

    @commands.check(checks.manage_messages_check)
    @commands.command()
    async def warnlist(self, ctx, user=None):
        """Show warnings for a user or display all warnings.

        `[p]warnlist @user`
        `[p]warnlist USER_ID`
        `[p]warnlist` **<-- This displays all warnings**"""
        view_all = False
        if not user:
            view_all = True
            if not (await dutils.prompt(ctx, "You are about to view a list of all warnings, proceeed?")):
                return await ctx.send("Cancelled viewing all warnings.")

        if not view_all:
            if ctx.message.mentions:
                member = ctx.message.mentions[0]
            elif user and user.isdigit():
                member = ctx.guild.get_member(int(user))
            else:
                member = None
            if not member:
                member = discord.utils.get(ctx.guild.members, name=user)
            if not member and not user.isdigit():
                return await ctx.send("Could not find this user.\n"
                                      "If the user left the server then "
                                      "the argument has to be an integer "
                                      "(user id basically) "
                                      "to view the left user's warns")
            if member:
                m_id = member.id
            else:
                m_id = user
                await ctx.send("User by provided id is not on the server anymore.")

            ws = [q for q in Actions.select().where(Actions.type == 'warn',
                                                    Actions.offender == m_id,
                                                    Actions.guild == ctx.guild.id).dicts()]
            if not ws:
                return await ctx.send("This user has no warnings.")
            ws = self.ws_to_usr_dict(ws)
            warn_arr = ws[m_id]
            title = f"Warnings for {f'{m_id} __(user not on the server)__' if not member else f'{member} ({m_id})'}"
            txt = []
            for w in warn_arr:
                responsible = ctx.guild.get_member(int(w['responsible']))
                if not responsible: responsible = m_id
                txt.append(f"\n\n**->** `{w['reason']}`\n"
                           f"*-by: {responsible}*\n"
                           f"*-on: {w['date'].strftime('%c')}*")
            txt = txt[::-1]
            desc = ""
            desc_arr = []
            while len(txt) > 0:
                desc += txt.pop()
                if len(desc) > 400:
                    desc_arr.append(desc)
                    desc = ""
            if desc: desc_arr.append(desc)

            embeds = []
            for i in range(len(desc_arr)):
                em = Embed(title=title + f'\nPage {i + 1}/{len(desc_arr)}',
                           description=desc_arr[i], color=0xf26338)
                if member: em.set_thumbnail(url=dutils.get_icon_url_for_member(member))
                em.set_footer(text='Times are in UTC')
                embeds.append(em)

            if len(embeds) == 1:
                await ctx.send(embed=embeds[0])
            else:
                await SimplePaginator(extras=embeds).paginate(ctx)

        else:
            ws = [q for q in Actions.select().where(Actions.type == 'warn',
                                                    Actions.guild == ctx.guild.id).dicts()]
            if not ws:
                return await ctx.send("This server didn't issue any warnings yet.")
            ws = self.ws_to_usr_dict(ws)
            toEmbed = []
            for k, v in ws.items():
                toEmbed.append([v[0]['user_display_name'], str(k), len(v)])
            embeds = []
            leng = 0
            done = False
            warns = sorted(toEmbed, key=itemgetter(2), reverse=True)
            headers = ['Name', 'Id', 'Count']
            i = 1
            while True:
                desc = []
                idxRange = 0
                for warn in warns:
                    destCpy = desc.copy()
                    warn[0] = warn[0][:10]
                    destCpy.append(warn)
                    cc = columnar(destCpy, headers, no_borders=True)
                    if len(cc) > 990: break
                    desc.append(warn)
                    idxRange += 1
                del warns[:idxRange]
                cc = columnar(desc, headers, no_borders=True)
                embeds.append(Embed(title=f"Warnlist display. Page {i}/[MAX]", description=f'\n```{cc}\n```'))
                if len(warns) == 0: break
                i += 1

            for e in embeds:
                e.title = str(e.title).replace("[MAX]", str(i))

            if len(embeds) == 1:
                await ctx.send(embed=embeds[0])
            else:
                await SimplePaginator(extras=embeds).paginate(ctx)

    @staticmethod
    def ws_to_usr_dict(ws):
        ret = {}
        for w in ws:
            if not w['offender'] in ret: ret[w['offender']] = []
            ret[w['offender']].append(w)
        return ret


def setup(bot):
    ext = Moderation(bot)
    bot.running_tasks.append(bot.loop.create_task(ext.if_you_need_loop()))
    bot.add_cog(ext)
