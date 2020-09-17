import asyncio
import datetime
import random

import discord
from discord.ext import commands
from discord import Member, Embed, File, utils
import os
import traceback
from models.claims import ClaimsManager, Claimed
from utils.dataIOa import dataIOa
import utils.checks as checks
import utils.discordUtils as dutils
import utils.timeStuff as tutils


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # _ in channel names is not allowed!!
        # if you want an - instead of a space prefix ch name with _
        self.data = {}
        self.config = dataIOa.load_json('settings/claims_settings.json')
        bot.loop.create_task(self.set_setup())
        self.just_claimed = {}

    async def set_setup(self):
        if not self.bot.is_ready():
            await self.bot.wait_until_ready()
        self.data = await ClaimsManager.get_data_from_server(self.bot, self.config)
        print(f'---{datetime.datetime.utcnow().strftime("%c")}---')
        print("Claims data loaded")

    @commands.group(aliases=['bride', 'vtuber'])
    async def claim(self, ctx):
        """Get your daily claim for a certain theme

        Command usages:
        `[p]claim` - shows this output
        `[p]bride` - get your bride
        `[p]vtuber` - get your daily vtuber

        Use subcommands for other functionalities
        """
        cmd = ctx.invoked_with
        if cmd == 'claim' or (cmd == 'claim' and ctx.invoked_subcommand is not None):
            raise commands.errors.BadArgument
        if cmd == 'bride':
            await self.do_claim(ctx, 'bride')
        if cmd == 'vtuber':
            await self.do_claim(ctx, 'vtuber')

    @claim.command()
    async def history(self, ctx):
        """a"""
        pass

    async def do_claim(self, ctx, c_type, claim_cd=20):
        if not self.data:
            return await ctx.send("Hold up a little bit, I'm still loading the data.")
        utcnow = datetime.datetime.utcnow()
        now = utcnow.timestamp()
        d_key = f"{ctx.author.id}_{c_type}"
        anti_spam_cd = 15
        # [invoked_times, invoked_at]
        if d_key in self.just_claimed:
            if now - self.just_claimed[d_key][1] < anti_spam_cd:
                self.just_claimed[d_key][0] += 1
                if self.just_claimed[d_key][0] > 2:  # the 3rd spam is nuke
                    out = f'[spamming {c_type} | {ctx.message.content}]({ctx.message.jump_url})'
                    await dutils.blacklist_from_bot(self.bot, ctx.message.author, out,
                                                    ctx.message.guild.id,
                                                    ch_to_reply_at=ctx.message.channel, arl=0)
                else:
                    await ctx.send(f"💢 {ctx.author.mention} stop spamming the "
                                   f"`{c_type}` command, or else!", delete_after=10)
            else:
                del self.just_claimed[d_key]
        else:
            self.just_claimed[d_key] = [0, now]

        if d_key in self.just_claimed and self.just_claimed[d_key][0] == 0:
            d = self.data[c_type]
            orig_key = random.choice(list(d))
            orig_key_split = orig_key.split('_')
            color = int(orig_key_split[1], 16)
            got = random.choice(d[orig_key][0])  # attachements list on index 0
            attachement = got[0]  # urls
            is_nsfw = got[1]

            usr = Claimed.select().where(Claimed.user == ctx.author.id,
                                         Claimed.type == c_type,
                                         Claimed.expires_on > utcnow)
            if usr:
                usr = usr.get()
                await ctx.send(f"You already have a claimed {c_type}. Please try again in "
                               f"**{tutils.convert_sec_to_smh((usr.expires_on - utcnow).total_seconds())}**")
            else:
                claim, created = Claimed.get_or_create(user=ctx.author.id, type=c_type)
                claim.expires_on = utcnow + datetime.timedelta(hours=claim_cd)
                claim.save()
                file = None
                em = Embed(title=f'**{orig_key_split[0]}**', color=color)
                if is_nsfw:
                    file = await attachement.to_file(spoiler=True, use_cached=True)
                    em.description = '⚠ potentially nsfw image'
                    em.set_footer(text='⚠ potentially nsfw image')
                    # em.set_image(url=f'attachment://{file.filename}')
                else:
                    em.set_image(url=attachement.url)

                await ctx.send(embed=em, content=f'Your {c_type} for the day is', file=file)

            # when done remove them if they aren't spamming anymore
            await asyncio.sleep(anti_spam_cd + 1)
            if d_key in self.just_claimed:
                del self.just_claimed[d_key]


def setup(bot):
    ext = Fun(bot)
    bot.add_cog(ext)
