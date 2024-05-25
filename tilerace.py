import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import csv
import sqlite3
import os
from datetime import datetime
from titlecase import titlecase

#guild = 532377514975428628
mod_role = "Tileracemod"
player_role = "Tileracer"

async def get_db(ctx):
    return f"databases/{ctx.guild.id}.db"


async def is_game_live(db):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check if the game is live
    cursor.execute("SELECT is_live FROM game_state WHERE id = 1")
    game_state = cursor.fetchone()
    conn.close()

    if game_state and game_state[0] == 1:
        return True
    return False

async def log_roll(team_id, user_id, roll_value, roll_type, db):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO roll_history (team_id, user_id, roll_value, roll_type) 
                      VALUES (?, ?, ?, ?)''', (team_id, user_id, roll_value, roll_type))
    conn.commit()
    conn.close()

async def roll_dice():
    return random.randint(1, 6)


async def give_chance_card(team_id, db, ctx):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Confirm the team
    cursor.execute("SELECT * FROM bingo_teams WHERE team_id = ?", (team_id,))
    team_data = cursor.fetchone()
    if not team_data:
        conn.close()
        print("team not found.")
        return
    team_name, logo, rerolls, skips, tile, chance_state, chance_task, previous_roll, tile_complete, broken_dice, get_out_of_jail, golden = team_data[1:]
    print(get_out_of_jail)
    if get_out_of_jail > 0:
        # Subtract one get out of jail card
        cursor.execute("UPDATE bingo_teams SET get_out_of_jail = ? WHERE team_id = ?", (get_out_of_jail - 1, team_id))
        await ctx.reply("You have a 'Get Out of Jail' card! The chance card effect has been negated.")
        conn.commit()
        conn.close()
        return

    # Give them a chance card
    cursor.execute("SELECT * FROM chance_tasks ORDER BY RANDOM() LIMIT 1")
    chance_task_id, chance = cursor.fetchone()
    if chance_task_id == 1:
        cursor.execute("UPDATE bingo_teams SET broken_dice = ? WHERE team_id = ?", (1, team_id))
    else:
        # Update the team's chance task
        cursor.execute("UPDATE bingo_teams SET chance_task = ? WHERE team_id = ?", (chance_task_id, team_id))

        # Change team's status to indicate chance card
        cursor.execute("UPDATE bingo_teams SET chance_state = 1 WHERE team_id = ?", (team_id,))

    # Close the connection before sending the message
    conn.commit()
    conn.close()

    # Construct the image path based on the task number
    image_path = f"chancecards/{chance_task_id}.png"

    # Open the image file as a discord.File object
    try:
        with open(image_path, "rb") as file:
            image = discord.File(file)
    except FileNotFoundError:
        print(f"Image file not found: {image_path}")
        return

    # Send message with chance card and image
    embed = discord.Embed(title="Chance Card", description=f"Your chance card is: {chance}", color=discord.Color.gold())

    # Send the message with embed and image file attached
    await ctx.reply(embed=embed, file=image)
    return


async def golden_tile(team, tile, db, ctx):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check if the tile has already been completed by any team
    cursor.execute("SELECT team_id FROM bingo_tasks_completed WHERE task_id = ?", (tile,))
    existing_completion = cursor.fetchone()

    if existing_completion:
        await ctx.reply("Unlucky! This Golden Ticket has already been claimed by another team. - Eat shit, you were too slow.")
        conn.close()
        return

    # add the golden ticket count by 1
    cursor.execute("SELECT golden FROM bingo_teams WHERE team_name = ?", (team,))
    current_golden_count = cursor.fetchone()[0]
    new_golden_count = current_golden_count + 1
    cursor.execute("UPDATE bingo_teams SET golden = ? WHERE team_name = ?", (new_golden_count, team))

    await ctx.reply("You have gained a golden ticket! Use it wisely! :)")
    conn.commit()
    conn.close()

    return


async def check_tile(team_id, tile, db):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    # Fetch the maximum task_id completed by the team
    cursor.execute("SELECT MAX(task_id) FROM bingo_tasks_completed WHERE team_id = ?", (team_id,))
    old_tile = cursor.fetchone()[0]
    if not old_tile:
        print("Has not completed any tiles, old tile must = 0")
        old_tile = 0
    print(f"old tile:{old_tile}")

    # Fetch the tasks between the old_tile and the new_tile
    cursor.execute("SELECT * FROM bingo_tasks WHERE task_id > ? AND task_id <= ?", (old_tile, tile))
    passed_tasks = cursor.fetchall()

    print("Passed tasks:")
    print(passed_tasks)

    # Check if any of the passed tasks are "brick" tiles
    for task in passed_tasks:
        if task[2] == "brick":
            # If a "brick" tile is passed, set the tile to the "brick" tile
            brick_tile_id = task[0]
            tile = brick_tile_id
            print("brick wall!!!")
            print(brick_tile_id)
            break  # Exit loop since we found a "brick" tile

    conn.close()
    return tile


async def check_skilling_tile_completion(team_id, skilling_tile_id, db):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check if the team has already completed the skilling tile
    cursor.execute("SELECT * FROM completed_skilling_tiles WHERE team_id = ? AND skilling_tile_id = ?",
                   (team_id, skilling_tile_id))
    result = cursor.fetchone()

    conn.close()

    return result is not None


class BingoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        for guilds in self.bot.guilds:
            db_file = f"databases/{guilds.id}.db"
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS bingo_teams (
                                team_id INTEGER PRIMARY KEY,
                                team_name TEXT,
                                logo TEXT,
                                rerolls INTEGER,
                                skips INTEGER,
                                tile INTEGER,
                                chance_state BOOLEAN,
                                chance_task INTEGER,
                                previous_roll INTEGER,
                                tile_complete BOOLEAN,
                                broken_dice BOOLEAN,
                                get_out_of_jail BOOLEAN,
                                golden INTEGER                                
                            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS bingo_players (
                                player_id INTEGER PRIMARY KEY,
                                discord_id INTEGER,
                                rsn TEXT,
                                team TEXT,
                                signup TEXT
                            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS bingo_tasks (
                                task_id INTEGER PRIMARY KEY,
                                task TEXT,
                                type TEXT
                            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS chance_tasks (
                                task_id INTEGER PRIMARY KEY,
                                task TEXT
                            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS bingo_tasks_completed (
                                task_id INTEGER,
                                team_id INTEGER,
                                proof TEXT,
                                completion_time TIMESTAMP
                            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS completed_skilling_tiles (
                                team_id INTEGER,
                                skilling_tile_id INTEGER,
                                PRIMARY KEY (team_id, skilling_tile_id)
                              )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS game_state (
                                id INTEGER PRIMARY KEY,
                                is_live BOOLEAN
                            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS roll_history (
                                      roll_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                      team_id INTEGER,
                                      user_id INTEGER,
                                      roll_value INTEGER,
                                      roll_type TEXT,
                                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                      FOREIGN KEY (team_id) REFERENCES bingo_teams(team_id),
                                      FOREIGN KEY (user_id) REFERENCES bingo_players(discord_id)
                                  );''')
            conn.commit()
            conn.commit()
            conn.close()


    @commands.hybrid_command(name="create_team", description="Create's a team for the upcoming bingo!")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.describe(team="Team Name to be created.")
    @app_commands.describe(logo="Logo for the team.")
    async def create_team(self, ctx: commands.Context, team: str, logo: discord.Attachment):
        if mod_role not in [role.name for role in ctx.author.roles]:
            await ctx.reply("You don't have the required role to use this command.")
            return
        team = titlecase(team)

        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        # Check if the team already exists
        cursor.execute("SELECT * FROM bingo_teams WHERE team_name = ?", (team,))
        existing_team = cursor.fetchone()
        if existing_team:
            await ctx.reply("A team with that name already exists.")
            conn.close()
            return

        # Insert the team into the database with default values
        cursor.execute(
            "INSERT INTO bingo_teams (team_name, logo,  rerolls, skips, tile, chance_state, chance_task, previous_roll, tile_complete, get_out_of_jail, golden) VALUES (?, ?, 2, 0, 0, 0, 0, 0, 1, 0, 0)",
            (team, str(logo),))
        conn.commit()
        conn.close()
        await ctx.reply(f"Team \"{team}\" created!")

    @commands.hybrid_command(name="start_game", description="Start the game and set it as live.")
    #@app_commands.guilds(discord.Object(id=guild))
    async def start_game(self, ctx: commands.Context):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        # Set the game as live
        cursor.execute("INSERT OR REPLACE INTO game_state (id, is_live) VALUES (1, 1)")
        conn.commit()
        conn.close()

        await ctx.send("The Tilerace game is live!! The codeword is \"Jimmyleg\"")

    @commands.hybrid_command(name="set_team", description="Assign a user to a team")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.describe(user="The @name of a discord user who is signing up.")
    @app_commands.describe(team="The name of the team the user is joining.")
    async def set_team(self, ctx: commands.Context, user: str, team: str):
        if mod_role not in [role.name for role in ctx.author.roles]:
            await ctx.reply("You don't have the required role to use this command.")
            return
        try:
            user_id = int(user.replace("<", "").replace(">", "").replace("@", "").replace("!", ""))
        except ValueError:
            await ctx.reply("Error with the username, make sure you have provided the users discord @ name :)")
            return
        mentioned_user = ctx.guild.get_member(user_id)
        team = titlecase(team)
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        # Check to make sure team exists
        cursor.execute("SELECT * FROM bingo_teams WHERE team_name = ?", (team,))
        existing_team = cursor.fetchone()
        if not existing_team:
            await ctx.reply(f"That team doesn't appear to exist.")
            return
        # Check if player already in a team
        cursor.execute("SELECT * FROM bingo_players WHERE discord_id = ?", (user_id,))
        existing_player = cursor.fetchone()
        print(existing_player)
        if not existing_player:
            await ctx.reply(f"User has not been signed up for the tile race!")
            return
        existing_team = existing_player[3]
        print(existing_team)
        if existing_team:
            await ctx.reply(f"User has already been assigned to team: {existing_team}")
            return
        cursor.execute("UPDATE bingo_players SET team = ? WHERE discord_id = ?",
                       (team, user_id))
        await ctx.reply(f"User {mentioned_user} has been added to team: {team}")
        conn.commit()
        conn.close()

    @commands.hybrid_command(name="tilerace_signup", description="Sign up for bingo!")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.describe(rsn="Your RuneScape name.")
    @app_commands.describe(proof="Screenshot of your buy in proof")
    async def tilerace_signup(self, ctx: commands.Context, rsn: str, proof: discord.Attachment):
        # Check if the user already signed up
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bingo_players WHERE discord_id = ?", (ctx.author.id,))
        existing_player = cursor.fetchone()
        if existing_player:
            await ctx.reply("You have already signed up for bingo.")
            conn.close()
            return

        # Insert the player into the database
        cursor.execute("INSERT INTO bingo_players (discord_id, rsn, team, signup) VALUES (?, ?, '', ?)",
                       (ctx.author.id, rsn, str(proof)))
        conn.commit()

        # Assign the "Tileracer" role to the player
        role = discord.utils.get(ctx.guild.roles, name="Tileracer")
        if role:
            await ctx.author.add_roles(role)
        conn.close()

        await ctx.reply(f"You have successfully signed up for bingo and been assigned the Tileracer role! {proof}")

    @commands.hybrid_command(name="tilerace_signup_other", description="Sign up another person for bingo!")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.describe(rsn="Your RuneScape name.")
    @app_commands.describe(discord_name="The discord @ of the other person you are signing up.")
    @app_commands.describe(proof="Screenshot of your buy in proof")
    async def tilerace_signup_other(self, ctx: commands.Context, discord_name: str, rsn: str,
                                    proof: discord.Attachment):
        if mod_role not in [role.name for role in ctx.author.roles]:
            await ctx.reply("You don't have the required role to use this command.")
            return
        try:
            user_id = int(discord_name.replace("<", "").replace(">", "").replace("@", "").replace("!", ""))
        except ValueError:
            await ctx.reply("Error with the username, make sure you have provided the users discord @ name :)")
            return
        print(user_id)
        # Check if the user already signed up
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bingo_players WHERE discord_id = ?", (user_id,))
        existing_player = cursor.fetchone()
        if existing_player:
            await ctx.reply("You have already signed up for bingo.")
            conn.close()
            return

        # Insert the player into the database
        cursor.execute("INSERT INTO bingo_players (discord_id, rsn, team, signup) VALUES (?, ?, '', ?)",
                       (user_id, rsn, str(proof)))
        conn.commit()

        # Assign the "Tileracer" role to the player
        role = discord.utils.get(ctx.guild.roles, name="Tileracer")
        if role:
            await ctx.author.add_roles(role)
        conn.close()

        await ctx.reply(f"You have successfully signed up for bingo and been assigned the Tileracer role! {proof}")

    @commands.hybrid_command(name="reset_tile_race", description="Reset the current Tilerace game. Be careful.")
    #@app_commands.guilds(discord.Object(id=guild))
    async def reset_tile_race(self, ctx: commands.Context):
        if mod_role not in [role.name for role in ctx.author.roles]:
            await ctx.reply("You don't have the required role to use this command.")
            return
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bingo_teams")
        cursor.execute("DELETE FROM bingo_players")
        cursor.execute("DELETE FROM bingo_tasks")
        cursor.execute("DELETE FROM chance_tasks")
        cursor.execute("DELETE FROM bingo_tasks_completed")
        conn.commit()
        conn.close()
        await ctx.reply("All tables cleared.")

    @commands.hybrid_command(name="roll_tile", description="Roll for a new tile!")
    #@app_commands.guilds(discord.Object(id=guild))
    async def roll_tile(self, ctx: commands.Context):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        if not await is_game_live(db):
            await ctx.send("The game is not live yet!")
            return

        # Check if the player exists in the bingo_players table
        cursor.execute("SELECT team FROM bingo_players WHERE discord_id = ?", (ctx.author.id,))
        player_data = cursor.fetchone()

        if player_data:
            team_name = player_data[0]  # Extracting team name

            if team_name:  # If team is not blank
                # Get the current tile of the team from bingo_teams table
                cursor.execute("SELECT * FROM bingo_teams WHERE team_name = ?", (team_name,))
                team_data = cursor.fetchone()
                team_id, team_name, logo, rerolls, skips, current_tile, chance_state, chance_task, previous_roll, tile_complete, broken_dice, jail_card, golden = team_data
                if tile_complete != 1:
                    await ctx.reply("Your team still needs to complete it's turn. Either /reroll or /complete.")
                    return
                if chance_state == 1:
                    await ctx.reply("your team still has to complete it's chance card!!")
                    return
                if broken_dice == 1:
                    roll = random.randint(1, 3)
                roll = await roll_dice()
                provisional_tile = current_tile + roll
                working_tile = await check_tile(team_id, provisional_tile, db)
                cursor.execute("SELECT task, type FROM bingo_tasks WHERE task_id = ?", (working_tile,))
                task, type_ = cursor.fetchone()
                new_tile = working_tile
                await log_roll(team_id, ctx.author.id, roll, 'roll', db)
                # Update the team's tile in the bingo_teams table
                cursor.execute(
                    "UPDATE bingo_teams SET tile = ?, tile_complete = ?, previous_roll = ? WHERE team_id = ?",
                    (new_tile, 0, roll, team_id))
                if type_ == "normal":
                    await ctx.reply(
                        f"You rolled a {roll}. Your team \"{team_name}\" is now onto tile: {new_tile} - ({task})")
                elif type_ == "brick":
                    await ctx.reply(
                        f"You rolled a {roll}. Ouch. You have rolled into a brick wall... Your team \"{team_name}\" is now onto tile: {new_tile} - ({task})")
                elif type_ == "chance":
                    await ctx.reply(
                        f"You rolled a {roll}. Your team \"{team_name}\" is now onto tile: {new_tile} - ({task}). Reminder this is a chance tile - you have the option to complete the tile or re-roll and take a risk. What will you choose?")
                elif type_ == "golden":
                    await ctx.reply(
                        f"You rolled a {roll}. Your team \"{team_name}\" is now onto a *golden tile* tile: {new_tile} - ({task}).")
            else:
                await ctx.reply(
                    "You aren't yet in any team, if this is a mistake contact <@210193458898403329> or one of the mods asap :)")
        else:
            await ctx.reply(
                "You aren't registered as a player, if this is a mistake contact <@210193458898403329> or one of the mods asap :)")
        conn.commit()
        conn.close()

    @commands.hybrid_command(name="reroll_tile", description="Uses one of your team's rerolls to roll again.")
    #@app_commands.guilds(discord.Object(id=guild))
    async def reroll_tile(self, ctx: commands.Context):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        # Check if the player exists in the bingo_players table
        cursor.execute("SELECT team FROM bingo_players WHERE discord_id = ?", (ctx.author.id,))
        player_data = cursor.fetchone()

        if player_data:
            team_name = player_data[0]  # Extracting team name

            if team_name:  # If team is not blank
                # Get the current tile of the team from bingo_teams table
                cursor.execute("SELECT * FROM bingo_teams WHERE team_name = ?", (team_name,))
                team_data = cursor.fetchone()
                team_id, team_name, logo, rerolls, skips, current_tile, chance_state, chance_task, previous_roll, tile_complete, broken_dice, jail_card, golden = team_data
                if tile_complete != 0:
                    await ctx.reply("Your team still needs to roll for a tile.")
                    return
                if chance_state == 1:
                    await ctx.reply("Your team still has to complete its chance card!!")
                    return

                # Deduct one reroll from the team's count
                if rerolls > 0:
                    rerolls -= 1
                    cursor.execute("UPDATE bingo_teams SET rerolls = ? WHERE team_id = ?", (rerolls, team_id))
                    conn.commit()
                else:
                    await ctx.reply("Your team has no more rerolls left!")
                    conn.commit()
                    conn.close()
                    return

                while True:
                    if broken_dice == 1:
                        roll = random.randint(1, 3)
                        if roll != previous_roll:
                            break
                    else:
                        roll = await roll_dice()
                        if roll != previous_roll:
                            break
                await log_roll(team_id, ctx.author.id, roll, 'reroll', db)
                cursor.execute("SELECT type FROM bingo_tasks WHERE task_id = ?", (current_tile,))
                old_tile_type = cursor.fetchone()[0]
                if old_tile_type == "chance":
                    await give_chance_card(team_id, db, ctx)

                cursor.execute("SELECT MAX(task_id) FROM bingo_tasks_completed WHERE team_id = ?", (team_id,))
                old_tile = cursor.fetchone()[0]
                cursor.execute("SELECT type FROM bingo_tasks WHERE task_id = ?", (old_tile,))
                provisional_tile = old_tile + roll
                working_tile = await check_tile(team_id, provisional_tile, db)
                cursor.execute("SELECT task, type FROM bingo_tasks WHERE task_id = ?", (working_tile,))
                task, type_ = cursor.fetchone()
                new_tile = working_tile

                # Update the team's tile in the bingo_teams table
                cursor.execute(
                    "UPDATE bingo_teams SET tile = ?, tile_complete = ?, previous_roll = ? WHERE team_id = ?",
                    (new_tile, 0, roll, team_id))

                if type_ == "normal":
                    await ctx.reply(
                        f"You rerolled a {roll}. Your team \"{team_name}\" is now onto tile: {new_tile} - ({task})")
                elif type_ == "brick":
                    await ctx.reply(
                        f"You rerolled a {roll}. Ouch. You have rolled into a brick wall... Your team \"{team_name}\" is now onto tile: {new_tile} - ({task})")
                elif type_ == "chance":
                    await ctx.reply(
                        f"You rerolled a {roll}. Your team \"{team_name}\" is now onto tile: {new_tile} - ({task}). Wait a second, this is a chance tile! To complete the tile or reroll and risk a chance card??!! :o")
            else:
                await ctx.reply(
                    "You aren't yet in any team. If this is a mistake, contact <@210193458898403329> or one of the mods asap :)")
        else:
            await ctx.reply(
                "You aren't registered as a player. If this is a mistake, contact <@210193458898403329> or one of the mods asap :)")
        conn.commit()
        conn.close()

    @commands.hybrid_command(name="complete_tile", description="Mark your teams tile as completed!!")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.describe(proof="Screenshot of your completed tile proof")
    async def complete_tile(self, ctx: commands.Context, proof: discord.Attachment, proof2: discord.Attachment = None,
                            proof3: discord.Attachment = None, proof4: discord.Attachment = None,
                            proof5: discord.Attachment = None):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT team FROM bingo_players WHERE discord_id = ?", (ctx.author.id,))
        player_data = cursor.fetchone()
        if not player_data:
            await ctx.reply("You aren't signed up for the tilerace!")
            return
        team_name = player_data[0]
        if not team_name:
            await ctx.reply("You aren't part of any team!")
            return
        cursor.execute("SELECT tile, chance_state, tile_complete, team_id FROM bingo_teams WHERE team_name = ?",
                       (team_name,))
        team_data = cursor.fetchone()
        current_tile, chance_state, team_state, team_id = team_data
        cursor.execute("SELECT type FROM bingo_tasks WHERE task_id = ?", (current_tile,))
        old_tile_type = cursor.fetchone()[0]
        if team_state == 1:
            await ctx.reply("Your team still needs to roll for a new tile!")
            return
        if chance_state == 1:
            await ctx.reply("You still have to complete your chance task before you can complete this tile!")
            return
        cursor.execute("UPDATE bingo_teams SET tile_complete = 1 WHERE team_id = ?", (team_id,))
        cursor.execute("INSERT INTO bingo_tasks_completed (task_id, team_id, proof, completion_time) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                       (current_tile, team_id, str(proof),))
        reply_message = f"You have marked your team's tile as complete! You may now roll for a new tile! {proof.url}"

        # Include additional proofs if they exist
        if proof2:
            reply_message += f" {proof2.url}"
        if proof3:
            reply_message += f" {proof3.url}"
        if proof4:
            reply_message += f" {proof4.url}"
        if proof5:
            reply_message += f" {proof5.url}"

        await ctx.reply(reply_message)
        if old_tile_type == 'golden':
            await golden_tile(team_name, current_tile, db, ctx)
        conn.commit()
        conn.close()

    @commands.hybrid_command(name="complete_chance", description="Mark your teams tile as completed!!")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.describe(proof="Screenshot of your completed tile proof")
    async def complete_chance(self, ctx: commands.Context, proof: discord.Attachment):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT team FROM bingo_players WHERE discord_id = ?", (ctx.author.id,))
        player_data = cursor.fetchone()
        if not player_data:
            await ctx.reply("You aren't signed up for the tilerace!")
            return
        team_name = player_data[0]
        if not team_name:
            await ctx.reply("You aren't part of any team!")
            return
        cursor.execute("SELECT tile, chance_state, tile_complete, team_id FROM bingo_teams WHERE team_name = ?",
                       (team_name,))
        team_data = cursor.fetchone()
        current_tile, chance_state, team_state, team_id = team_data
        if chance_state == 0:
            await ctx.reply("You don't need to complete a chance task :)")
            return
        cursor.execute("UPDATE bingo_teams SET chance_state = 0 WHERE team_id = ?", (team_id,))
        await ctx.reply(f"You have completed your chance task :) {proof}")
        conn.commit()
        conn.close()

    @commands.hybrid_command(name="upload_bingo_tasks", description="Upload the task list for your tilerace game!")
    #@app_commands.guilds(discord.Object(id=guild))
    async def upload_bingo_tasks(self, ctx: commands.Context, tasks: discord.Attachment):
        if mod_role not in [role.name for role in ctx.author.roles]:
            await ctx.reply("You don't have the required role to use this command.")
            return
        db = await get_db(ctx)
        # Connect to the SQLite database
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        await tasks.save("bingo_tasks.csv")
        cursor.execute('''DELETE FROM bingo_tasks''')
        # Open the CSV file for reading
        with open("bingo_tasks.csv", 'r') as file:
            csv_reader = csv.reader(file)

            # go over each line in the CSV file
            for row in csv_reader:
                task, type_ = row

                # Insert values into the bingo_tasks table
                cursor.execute('''INSERT INTO bingo_tasks (task, type)
                                  VALUES (?, ?)''', (task, type_))

        # Commit the changes and close the database connection
        conn.commit()
        conn.close()
        await ctx.reply("Task list successfully uploaded.")

    @commands.hybrid_command(name="upload_chance_tasks", description="Upload the chances task list for your tilerace game!")
    #@app_commands.guilds(discord.Object(id=guild))
    async def upload_chance_tasks(self, ctx: commands.Context, tasks: discord.Attachment):
        if mod_role not in [role.name for role in ctx.author.roles]:
            await ctx.reply("You don't have the required role to use this command.")
            return
        db = await get_db(ctx)
        # Connect to the SQLite database
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        await tasks.save("chance_tasks.csv")
        cursor.execute('''DELETE FROM chance_tasks''')
        # Open the CSV file for reading
        with open("chance_tasks.csv", 'r') as file:
            csv_reader = csv.reader(file)

            # Iterate over each line in the CSV file
            for row in csv_reader:
                # Parse values from the CSV row
                task = row

                # Insert values into the bingo_tasks table
                cursor.execute('''INSERT INTO chance_tasks (task)
                                      VALUES (?)''', task)

        # Commit the changes and close the database connection
        conn.commit()
        conn.close()
        await ctx.reply("Task list successfully uploaded.")

    @commands.hybrid_command(name="list_bingo_tasks", description="Display all available tasks along with their types.")
    #@app_commands.guilds(discord.Object(id=guild))
    async def list_bingo_tasks(self, ctx: commands.Context):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        cursor.execute('''SELECT * FROM bingo_tasks''')
        tasks = cursor.fetchall()
        conn.close()

        # Check if there are tasks available
        if tasks:
            file_name = f"{ctx.guild.id}_task_list.txt"
            with open(file_name, "w") as file:
                file.write("Available tasks:\n")
                for task in tasks:
                    tile, task, type_ = task
                    file.write(f"({tile}) - {task} - {type_}\n")

            # Send the text file
            with open(file_name, "rb") as file:
                await ctx.reply(file=discord.File(file, filename=file_name))
        else:
            await ctx.send("No tasks available.")

    @commands.hybrid_command(name="show_teams", description="Display all teams along with their players.")
    #@app_commands.guilds(discord.Object(id=guild))
    async def show_teams(self, ctx: commands.Context):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        # Fetch all teams and their players
        cursor.execute(
            "SELECT team_name, player_id, rsn FROM bingo_teams LEFT JOIN bingo_players ON bingo_teams.team_name = bingo_players.team")
        teams_data = cursor.fetchall()

        if not teams_data:
            await ctx.send("No teams or players found.")
            conn.close()
            return

        # Organize data by team
        teams_dict = {}
        for team_name, player_id, rsn in teams_data:
            if team_name not in teams_dict:
                teams_dict[team_name] = []
            if player_id:
                teams_dict[team_name].append(rsn)

        # Create an embed to display the teams and their players
        embed = discord.Embed(title="Teams and Players", color=discord.Color.blue())

        for team_name, players in teams_dict.items():
            players_list = "\n".join(players) if players else "No players in this team."
            embed.add_field(name=team_name, value=players_list, inline=False)

        await ctx.send(embed=embed)
        conn.close()

    @commands.hybrid_command(name="tilerace_leaderboard",
                             description="Display the current leaderboard for the bingo game.")
    #@app_commands.guilds(discord.Object(id=guild))
    async def tilerace_leaderboard(self, ctx: commands.Context):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        # Retrieve team data, corresponding tile names, and count of completed tiles
        cursor.execute("""
            SELECT bt.team_name, bt.tile, btsk.task, COUNT(btc.task_id)
            FROM bingo_teams bt
            LEFT JOIN bingo_tasks btsk ON bt.tile = btsk.task_id
            LEFT JOIN bingo_tasks_completed btc ON bt.team_id = btc.team_id
            GROUP BY bt.team_id
            ORDER BY bt.tile DESC
        """)
        teams_data = cursor.fetchall()
        conn.close()

        embed = discord.Embed(title="Tilerace Leaderboard", color=discord.Color.blue(),
                              description="Oooooh, I wonder who is winning?!?! Find out below:")


        if teams_data:
            for index, (team_name, tile, task_name, tiles_completed) in enumerate(teams_data, start=1):
                task_name = task_name if task_name else "Unknown Task"
                embed.add_field(
                    name=f"{index} - {team_name}",
                    value=f"Current tile: {tile}\n{task_name}\nTiles completed: {tiles_completed}",
                    inline=True
                )
        else:
            embed.description = "No teams found."

        embed.set_footer(text=datetime.now().strftime("%m/%d/%Y %I:%M %p"))

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="tilerace_profile", description="Display the profile of a user or a team.")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.describe(identifier="The name of the team or the Discord @ of the user.")
    async def tilerace_profile(self, ctx: commands.Context, identifier: str = None):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        if identifier is None:
            user_id = ctx.author.id

        else:
            if identifier.startswith("<@") and identifier.endswith(">"):
                try:
                    user_id = int(identifier.replace("<", "").replace(">", "").replace("@", "").replace("!", ""))
                except ValueError:
                    await ctx.reply("Invalid user mentioned.")
                    return

        cursor.execute("SELECT team FROM bingo_players WHERE discord_id = ?", (user_id,))
        player_data = cursor.fetchone()

        if not player_data:
            await ctx.reply("User is not signed up for the tilerace.")
            return

        identifier = player_data[0]

        # Retrieve team data from bingo_teams table
        cursor.execute("SELECT * FROM bingo_teams WHERE team_name = ?", (identifier,))
        team_data = cursor.fetchone()
        conn.close()

        embed = discord.Embed(title=f"Profile for {identifier}", color=discord.Color.green())

        if team_data:
            team_id, team_name, logo, rerolls, skips, tile, chance_state, chance_task, previous_roll, tile_complete, broken_dice, jail_card, golden = team_data

            embed.add_field(name="Team Name", value=team_name, inline=False)
            embed.add_field(name="Rerolls", value=rerolls, inline=True)
            embed.add_field(name="Current Tile", value=tile, inline=True)
            embed.add_field(name="Golden Tickets", value=golden, inline=False)
            embed.add_field(name="Get out of Jail Card", value=jail_card, inline=True)

            if logo:
                embed.set_thumbnail(url=logo)

        else:
            embed.description = "No team found with that name."

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="manage_team", description="Manage a team's members, rerolls, and tiles.")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.choices(edit=[
        discord.app_commands.Choice(name="Add Users", value=1),
        discord.app_commands.Choice(name="Edit Rerolls", value=2),
        discord.app_commands.Choice(name="Set Tile", value=3),
        discord.app_commands.Choice(name="Give Reroll", value=4)
    ])
    async def manage_team(self, ctx: commands.Context, team: str, edit: discord.app_commands.Choice[int],
                          value: int = None):
        if mod_role not in [role.name for role in ctx.author.roles]:
            await ctx.reply("You don't have the required role to use this command.")
            return

        team = titlecase(team)
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        # Check if the team exists
        cursor.execute("SELECT * FROM bingo_teams WHERE team_name = ?", (team,))
        existing_team = cursor.fetchone()
        if not existing_team:
            await ctx.reply(f"That team doesn't appear to exist.")
            conn.close()
            return

        if edit.value == 1:
            cursor.execute("SELECT rsn FROM bingo_players")
            players = [player[0] for player in cursor.fetchall()]

            # Split the players into chunks of 25
            player_chunks = [players[i:i + 25] for i in range(0, len(players), 25)]

            # Create dropdowns for each chunk
            dropdowns = []
            for chunk in player_chunks:
                max_values = min(10, len(chunk))  # Calculate max_values dynamically
                dropdown = discord.ui.Select(
                    placeholder="Select users to add.",
                    options=[discord.SelectOption(label=player, value=player) for player in chunk],
                    min_values=1,
                    max_values=max_values
                )
                dropdowns.append(dropdown)

            view = discord.ui.View(timeout=60)

            async def on_timeout():
                await ctx.send("Time to select users has expired.")

            async def my_callback(interaction):
                selected_users = interaction.data['values']
                for user in selected_users:
                    cursor.execute("UPDATE bingo_players SET team = ? WHERE rsn = ?", (team, user))
                    conn.commit()

                await interaction.response.send_message(content="Users updated.", ephemeral=True)
                conn.close()

            for dropdown in dropdowns:
                dropdown.callback = my_callback
                view.add_item(dropdown)

            view.on_timeout = on_timeout
            await ctx.send("Select users to update:", view=view)

        elif edit.value == 2:  # Edit Rerolls
            cursor.execute("UPDATE bingo_teams SET rerolls = ? WHERE team_name = ?", (value, team))
            conn.commit()
            await ctx.send(f"{team} rerolls updated to {value}.")
            conn.close()

        elif edit.value == 3:  # Set Tile
            cursor.execute("UPDATE bingo_teams SET tile = ? WHERE team_name = ?", (value, team))
            conn.commit()
            await ctx.send(f"{team} tile updated to {value}.")
            conn.close()

        elif edit.value == 4:  # Give Reroll
            cursor.execute("SELECT rerolls FROM bingo_teams WHERE team_name = ?", (team,))
            current_rerolls = cursor.fetchone()[0]
            new_rerolls = current_rerolls + value
            cursor.execute("UPDATE bingo_teams SET rerolls = ? WHERE team_name = ?", (new_rerolls, team))
            conn.commit()
            await ctx.send(f"{team} has been given {value} rerolls. Total rerolls: {new_rerolls}.")
            conn.close()

    @commands.hybrid_command(name="use_golden_ticket", description="Use your golden ticket to knock a team back!")
    #@app_commands.guilds(discord.Object(id=guild))
    async def use_golden_ticket(self, ctx: commands.Context, target_team: str):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        # Get the team of the Discord user issuing the command
        cursor.execute("SELECT team FROM bingo_players WHERE discord_id = ?", (ctx.author.id,))
        player_data = cursor.fetchone()

        if not player_data:
            await ctx.send("You are not associated with any team.")
            conn.close()
            return

        user_team = player_data[0]

        # Check if the user's team has a golden ticket
        cursor.execute("SELECT golden FROM bingo_teams WHERE team_name = ?", (user_team,))
        golden_ticket_data = cursor.fetchone()

        if not golden_ticket_data or golden_ticket_data[0] < 1:
            await ctx.send("Your team does not have a golden ticket.")
            conn.close()
            return

        # Check if the target team exists
        cursor.execute("SELECT team_name FROM bingo_teams WHERE team_name = ?", (target_team,))
        target_team_data = cursor.fetchone()

        if not target_team_data:
            await ctx.send("Target team not found.")
            conn.close()
            return

        target_team = target_team_data[0]

        # Fetch the current tile of the target team
        cursor.execute("SELECT tile, team_id FROM bingo_teams WHERE team_name = ?", (target_team,))
        target_team_tile_data = cursor.fetchone()
        target_tile, target_team_id = target_team_tile_data
        await ctx.send(
            f"{target_team} will drop down 1 tile unless they complete their current tile in 30 minutes!.")

        async def drop_tile_later():
            await asyncio.sleep(10)  # 30 minutes in seconds
            # Check if the target team has completed the tile
            conn = sqlite3.connect(db)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bingo_tasks_completed WHERE team_id = ? AND task_id = ?",
                           (target_team_id, target_tile))
            completed = cursor.fetchone()

            if not completed:
                # Move the target team back one tile
                new_tile = max(0, target_tile - 1)  # Ensure the new tile is not negative
                cursor.execute("UPDATE bingo_teams SET tile = ? WHERE team_id = ?", (new_tile, target_team_id))
                conn.commit()
                await ctx.send(f"{target_team} has been moved back to tile {new_tile}.")
            else:
                await ctx.send(f"{target_team} has completed their tile. They avoided the move back!")

        # Decrement the golden ticket count by 1
        cursor.execute("UPDATE bingo_teams SET golden = golden - 1 WHERE team_name = ?", (user_team,))
        conn.commit()

        asyncio.create_task(drop_tile_later())
        conn.close()

    @commands.hybrid_command(name="tilerace_stats", description="Shows various statistics about the tilerace game.")
    async def tilerace_stats(self, ctx: commands.Context):
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        # Most common roll
        cursor.execute(
            "SELECT roll_value, COUNT(*) as roll_count FROM roll_history GROUP BY roll_value ORDER BY roll_count DESC LIMIT 1")
        most_common_roll = cursor.fetchone()

        # Least common roll
        cursor.execute(
            "SELECT roll_value, COUNT(*) as roll_count FROM roll_history GROUP BY roll_value ORDER BY roll_count ASC LIMIT 1")
        least_common_roll = cursor.fetchone()

        # Luckiest rolling team (average roll)
        cursor.execute("""
            SELECT team_name, AVG(roll_value) as avg_roll
            FROM roll_history
            JOIN bingo_players ON roll_history.user_id = bingo_players.discord_id
            JOIN bingo_teams ON bingo_players.team = bingo_teams.team_name
            GROUP BY team_name
            ORDER BY avg_roll DESC LIMIT 1
        """)
        luckiest_team = cursor.fetchone()

        # Unluckiest rolling team (average roll)
        cursor.execute("""
            SELECT team_name, AVG(roll_value) as avg_roll
            FROM roll_history
            JOIN bingo_players ON roll_history.user_id = bingo_players.discord_id
            JOIN bingo_teams ON bingo_players.team = bingo_teams.team_name
            GROUP BY team_name
            ORDER BY avg_roll ASC LIMIT 1
        """)
        unluckiest_team = cursor.fetchone()

        # Luckiest rolling player (average roll)
        cursor.execute(
            "SELECT user_id, AVG(roll_value) as avg_roll FROM roll_history GROUP BY user_id ORDER BY avg_roll DESC LIMIT 1")
        luckiest_player = cursor.fetchone()

        # Unluckiest rolling player (average roll)
        cursor.execute(
            "SELECT user_id, AVG(roll_value) as avg_roll FROM roll_history GROUP BY user_id ORDER BY avg_roll ASC LIMIT 1")
        unluckiest_player = cursor.fetchone()

        # Most time spent on a tile
        cursor.execute("""
            SELECT team_name, task_id, MAX(completion_time) - MIN(completion_time) as max_time
            FROM bingo_tasks_completed
            JOIN bingo_teams ON bingo_tasks_completed.team_id = bingo_teams.team_id
            GROUP BY team_name, task_id
            ORDER BY max_time DESC LIMIT 1
        """)
        most_time_tile = cursor.fetchone()

        # Least time spent on a tile
        cursor.execute("""
            SELECT team_name, task_id, MAX(completion_time) - MIN(completion_time) as min_time
            FROM bingo_tasks_completed
            JOIN bingo_teams ON bingo_tasks_completed.team_id = bingo_teams.team_id
            GROUP BY team_name, task_id
            ORDER BY min_time ASC LIMIT 1
        """)
        least_time_tile = cursor.fetchone()

        conn.close()

        embed = discord.Embed(title="Tilerace Statistics", color=discord.Color.green())

        if most_common_roll:
            embed.add_field(name="Most Common Roll", value=f"{most_common_roll[0]} ({most_common_roll[1]} times)",
                            inline=False)
        if least_common_roll:
            embed.add_field(name="Least Common Roll", value=f"{least_common_roll[0]} ({least_common_roll[1]} times)",
                            inline=False)
        if luckiest_team:
            embed.add_field(name="Luckiest Team (Average Roll)",
                            value=f"{luckiest_team[0]} (Avg Roll: {luckiest_team[1]:.2f})", inline=False)
        if unluckiest_team:
            embed.add_field(name="Unluckiest Team (Average Roll)",
                            value=f"{unluckiest_team[0]} (Avg Roll: {unluckiest_team[1]:.2f})", inline=False)
        if luckiest_player:
            embed.add_field(name="Luckiest Player (Average Roll)",
                            value=f"<@{luckiest_player[0]}> (Avg Roll: {luckiest_player[1]:.2f})", inline=False)
        if unluckiest_player:
            embed.add_field(name="Unluckiest Player (Average Roll)",
                            value=f"<@{unluckiest_player[0]}> (Avg Roll: {unluckiest_player[1]:.2f})", inline=False)
        if most_time_tile:
            embed.add_field(name="Most Time Spent on a Tile",
                            value=f"Team: {most_time_tile[0]}, Task ID: {most_time_tile[1]}, Time: {most_time_tile[2]}",
                            inline=False)
        if least_time_tile:
            embed.add_field(name="Least Time Spent on a Tile",
                            value=f"Team: {least_time_tile[0]}, Task ID: {least_time_tile[1]}, Time: {least_time_tile[2]}",
                            inline=False)

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="bonus_tile", description="Mark a skilling tile as complete to get your bonus!")
    #@app_commands.guilds(discord.Object(id=guild))
    @app_commands.choices(skilling_tile=[
        discord.app_commands.Choice(name="1M Agility XP", value=1),
        discord.app_commands.Choice(name="1M Runecrafting XP", value=2),
        discord.app_commands.Choice(name="2M Woodcutting XP", value=3),
        discord.app_commands.Choice(name="1M Mining XP", value=4)
    ])
    async def bonus_tile(self, ctx: commands.Context, skilling_tile: discord.app_commands.Choice[int],
                         proof: discord.Attachment):
        print(skilling_tile.value)
        skilling_tile_id = skilling_tile.value
        db = await get_db(ctx)
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        cursor.execute("SELECT team FROM bingo_players WHERE discord_id = ?", (ctx.author.id,))
        player_data = cursor.fetchone()
        if not player_data:
            await ctx.reply("You aren't signed up for the tilerace!")
            return

        team_name = player_data[0]
        if not team_name:
            await ctx.reply("You aren't part of any team!")
            return

        cursor.execute(
            "SELECT tile, chance_state, tile_complete, team_id, rerolls, get_out_of_jail, golden FROM bingo_teams WHERE team_name = ?",
            (team_name,))
        team_data = cursor.fetchone()
        current_tile, chance_state, tile_complete, team_id, rerolls, get_out_of_jail, golden = team_data

        # Check if the team has already completed the skilling tile
        if await check_skilling_tile_completion(team_id, skilling_tile_id, db):
            conn.close()
            await ctx.reply("Your team has already completed this skilling tile.")
            return

        bonus_message = ""
        if skilling_tile.value in (1, 2):
            rerolls += 1
            cursor.execute("UPDATE bingo_teams SET rerolls = ? WHERE team_id = ?", (rerolls, team_id))
            bonus_message = "Your team has received a bonus reroll!"
        elif skilling_tile.value == 3:
            get_out_of_jail += 1
            cursor.execute("UPDATE bingo_teams SET get_out_of_jail = ? WHERE team_id = ?", (get_out_of_jail, team_id))
            bonus_message = "Your team has received a Get Out of Jail card!"
        elif skilling_tile.value == 4:
            golden += 1
            cursor.execute("UPDATE bingo_teams SET golden = ? WHERE team_id = ?", (golden, team_id))
            bonus_message = "Your team has received a Golden Ticket!"

        # Update the completed skilling tiles table
        cursor.execute("INSERT INTO completed_skilling_tiles (team_id, skilling_tile_id) VALUES (?, ?)",
                       (team_id, skilling_tile_id))

        await ctx.reply(f"Congrats on finishing your bonus tile! {bonus_message}")

        conn.commit()
        conn.close()
async def setup(bot):
    await bot.add_cog(BingoCommands(bot))
