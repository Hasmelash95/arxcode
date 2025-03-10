"""
Tests for different general commands.
"""

from mock import Mock, patch, PropertyMock
from datetime import datetime, timedelta

from evennia.server.models import ServerConfig
from server.utils.test_utils import (
    ArxCommandTest,
    TestEquipmentMixins,
    TestTicketMixins,
)
from world.crafting.models import CraftingRecipe, CraftingMaterialType
from world.dominion.domain.models import Army
from world.dominion.models import RPEvent, Organization, Member
from world.dominion.plots.models import (
    PlotAction,
    Plot,
    ActionRequirement,
    ActionPerEpisode,
)
from world.magic.models import SkillNode, Spell
from world.templates.models import Template
from web.character.models import PlayerAccount, Clue, Revelation, Episode

from typeclasses.readable.readable_commands import CmdWrite
from world.traits.models import Trait

from commands.base_commands import (
    story_actions,
    overrides,
    social,
    staff_commands,
    roster,
    crafting,
    jobs,
    xp,
    help as cmd_help,
    general,
    exchanges,
)


class CraftingTests(TestEquipmentMixins, ArxCommandTest):
    paccount1 = None
    paccount2 = None
    template1 = None
    template2 = None

    def setUp(self):
        super().setUp()
        self.paccount1 = PlayerAccount.objects.create(email="myawesome_email@test.org")
        self.paccount2 = PlayerAccount.objects.create(
            email="myawesome_email_2@test.org"
        )

        self.char1.roster.current_account = self.paccount1
        self.char1.roster.save()

        self.char2.roster.current_account = self.paccount2
        self.char2.roster.save()

        self.char2.sessions.add(self.session)

        self.template1 = Template(
            owner=self.paccount1,
            desc="This is a templated description! It is so awesome",
            attribution="freddy",
            apply_attribution=True,
            title="cool template",
            access_level="PR",
        )

        self.template2 = Template(
            owner=self.paccount1,
            desc="This is a templated description! It is so awesome",
            attribution="freddy",
            apply_attribution=True,
            title="cool template",
            access_level="RS",
        )

        self.template1.save()
        self.template2.save()

    def test_craft_with_templates(self):

        recipe = CraftingRecipe.objects.create(name="Thing", ability="all")

        self.char1.dompc.assets.crafting_recipes.add(recipe)
        self.char2.dompc.assets.crafting_recipes.add(recipe)

        self.assertEquals(self.template1.applied_to.count(), 0)

        self.setup_cmd(crafting.CmdCraft, self.char1)
        self.call_cmd("{}".format(recipe.name), None)
        self.call_cmd("/name object", None)
        self.call_cmd("/desc [[TEMPLATE_1]]", "Desc set to:\n[[TEMPLATE_1]]")
        self.call_cmd("/finish", None)

        created_obj = self.char1.contents[0]

        self.assertEquals(self.template1.applied_to.count(), 1)

        self.assertEqual(created_obj.desc, "[[TEMPLATE_1]]")
        self.assertEqual(self.template1.applied_to.get(), created_obj)

        created_obj.return_appearance(self.char1)

        self.assertIsNotNone(created_obj.ndb.cached_template_desc)

        self.template1.save()

        self.assertIsNone(created_obj.ndb.cached_template_desc)

        self.setup_cmd(crafting.CmdCraft, self.char2)
        self.call_cmd("{}".format(recipe.name), None)
        self.call_cmd("/name object", None)
        self.call_cmd(
            "/desc [[TEMPLATE_1]] and [[TEMPLATE_2]]",
            "You attempted to add the following templates that you do not have access to: [[TEMPLATE_1]], [[TEMPLATE_2]] to your desc.",
        )

        self.template1.save()

    def test_write(self):

        from evennia.utils import create

        typeclass = "typeclasses.readable.readable.Readable"

        book1 = create.create_object(
            typeclass=typeclass, key="book1", location=self.char1, home=self.char1
        )

        self.assertEquals(book1.contained_written_works.count(), 0)
        self.assertEquals(self.char1.authored_works.count(), 0)

        self.setup_cmd(CmdWrite, self.char1)
        self.call_cmd("Everybody dies", "Title: \nBody:\nEverybody dies", obj=book1)
        self.call_cmd("/title Rocks Fall", None, obj=book1)
        self.call_cmd("/finish", None, obj=book1)
        self.call_cmd(
            "/add book1=1,1", "You have added Rocks Fall as Chapter 1.", obj=book1
        )

        self.assertEquals(book1.contained_written_works.count(), 1)
        self.assertEquals(self.char1.authored_works.count(), 1)

    def test_cmd_recipes(self):
        self.setup_cmd(crafting.CmdRecipes, self.char2)
        self.instance.display_recipes = (
            Mock()
        )  # this builds a table & sends it to arx_more
        rtable = self.instance.display_recipes
        self.call_cmd("/cost Bag", "It will cost nothing for you to learn Bag.")
        self.add_recipe_additional_costs(10)
        self.char2.currency = 1
        self.call_cmd(
            "/learn Mask", "You have 1 silver. It will cost 10 for you to learn Mask."
        )
        self.char2.currency = 100
        self.call_cmd("/learn Mask", "You have learned Mask for 10 silver.")
        self.assertEqual(
            list(self.char2.dompc.assets.crafting_recipes.all()), [self.recipe6]
        )
        self.assertEqual(self.char2.currency, 90.0)
        self.call_cmd(
            "/info Mask",
            "Name: Mask\nDescription: \nSilver: 10\nMaterials: Mat1: 4(0/4)",
        )
        self.call_cmd("/learn", "Recipes you can learn:")
        rtable.assert_called_with(
            [
                self.recipe1,
                self.recipe2,
                self.recipe3,
                self.recipe4,
                self.recipe5,
                self.recipe7,
            ]
        )
        self.call_cmd("tailor", "")
        rtable.assert_called_with([self.recipe1])
        self.call_cmd("/known", "")
        rtable.assert_called_with([self.recipe6])
        self.match_recipe_locks_to_level()  # recipe locks become level-appropriate
        self.call_cmd("", "")
        rtable.assert_called_with([self.recipe6])
        self.call_cmd("/learn Bag", "You cannot learn 'Bag'. Recipes you can learn:")
        rtable.assert_called_with([])
        self.call_cmd(
            "/teach Char=Mask", "You cannot teach 'Mask'. Recipes you can teach:"
        )
        rtable.assert_called_with([])
        self.recipe6.locks.replace("teach:all();learn: ability(4)")
        self.recipe6.save()
        self.call_cmd("/teach Char=Mask", "They cannot learn Mask.")
        self.recipe6.locks.replace("teach:all();learn:all()")
        self.recipe6.save()
        self.call_cmd("/teach Char=Mask", "Taught Char Mask.")
        self.assertEqual(
            list(self.char.dompc.assets.crafting_recipes.all()), [self.recipe6]
        )
        self.call_cmd("/teach Char=Mask", "They already know Mask.")
        self.recipe5.locks.replace("teach:all();learn:all()")
        self.recipe5.save()
        self.caller = self.char  # Char is staff
        self.call_cmd(
            "/cost Hairpins", "It will cost nothing for you to learn Hairpins."
        )


class StoryActionTests(ArxCommandTest):
    def tearDown(self):
        ActionRequirement.objects.all().delete()
        super().tearDown()

    @classmethod
    def setUpTestData(cls):
        Trait.objects.get_or_create(name="strength", trait_type=Trait.STAT)
        Trait.objects.get_or_create(name="athletics", trait_type=Trait.SKILL)
        cls.current_account = PlayerAccount.objects.create(email="asdf@example.com")
        cls.episode = Episode.objects.create(name="asdf")

    def setUp(self):
        super().setUp()
        self.account1.roster.current_account = self.current_account
        self.account1.roster.save()

    @patch("world.dominion.plots.models.inform_staff")
    @patch("world.dominion.plots.models.get_week")
    def test_cmd_action(self, mock_get_week, mock_inform_staff):
        mock_get_week.return_value = 1
        self.setup_cmd(story_actions.CmdAction, self.account)
        self.crisis = Plot.objects.create(name="Test Crisis")
        self.call_cmd("/newaction", "You need to include a story.")
        self.caller.pay_action_points = Mock(return_value=False)
        self.call_cmd("/newaction testing", "You do not have enough action points.")
        self.caller.pay_action_points = Mock(return_value=True)
        self.call_cmd(
            "/newaction test crisis=testing",
            "You have drafted a new action (#1) to respond to Test Crisis: "
            "testing|Please note that you cannot invite players to an "
            "action once it is submitted.",
        )
        action = self.dompc.actions.last()
        self.call_cmd(
            "/submit 1", "Incomplete fields: ooc intent, tldr, roll, category"
        )
        self.call_cmd(
            "/category 1=foo",
            "You need to include one of these categories: combat, "
            "diplomacy, research, sabotage, scouting, support, unknown.",
        )
        self.call_cmd("/category 1=Research", "category set to Research.")
        self.call_cmd("/category 1=combat", "category set to Combat.")
        self.call_cmd(
            "/ooc_intent 1=testooc", "You have set your ooc intent to be: testooc"
        )
        self.assertEquals(action.questions.first().is_intent, True)
        self.call_cmd("/tldr 1=summary", "topic set to summary.")
        self.call_cmd("/roll 1=foo,bar", "You must provide a valid stat and skill.")
        self.call_cmd(
            "/roll 1=Strength,athletics",
            "stat set to strength.|skill set to athletics.",
        )
        self.call_cmd("/setsecret 1=sekrit", "Secret actions set to sekrit.")
        self.call_cmd("/invite 1=foo", "Could not find 'foo'.")
        self.call_cmd(
            "/invite 1=TestAccount2",
            "You must select an org before inviting players to the action.",
        )
        org = Organization.objects.create(name="test org")
        Member.objects.create(player=self.dompc, organization=org, rank=2)
        self.call_cmd(
            "/org 1=test org",
            "You have set test org to be the org for this crisis action. Orgs can only respond to one crisis per episode.",
        )
        self.call_cmd(
            "/invite 1=TestAccount2",
            "They must be an active member of test org to be invited to the action.",
        )
        Member.objects.create(player=self.dompc2, organization=org, rank=2)
        self.call_cmd(
            "/invite 1=TestAccount2",
            "You have invited Testaccount2 to join your action.",
        )
        self.caller = self.account2
        self.caller.pay_action_points = Mock(return_value=False)
        self.call_cmd(
            "/setaction 1=test assist", "You do not have enough action points."
        )
        self.caller.pay_action_points = Mock(return_value=True)
        self.call_cmd(
            "/setaction 1=test assist",
            "Action by test org for Test Crisis now has your assistance: test assist",
        )
        Army.objects.create(name="test army", owner=self.assetowner)
        # check for adding things to meet requirements
        self.call_cmd("/add 1=army,1", "There isn't an unmet requirement for army.")
        action.requirements.create(
            requirement_type=ActionRequirement.FORCES, requirement_text="Add some doodz"
        )
        self.call_cmd(
            "/add 1=army,1",
            "You don't have access to that Army.|Failed to send orders to the army.",
        )
        self.call_cmd("/readycheck 1", "Only the action leader can use that switch.")
        self.caller = self.account
        # check adding resource-type requirements
        self.call_cmd("/add 1=foo,bar", "Invalid type of resource.")
        self.call_cmd("/add 1=ap,50", "There isn't an unmet requirement for ap.")
        req = action.requirements.create(
            requirement_type=ActionRequirement.AP,
            max_rate=25,
            weekly_total=25,
            total_required_amount=50,
        )
        self.call_cmd(
            "/add 1=ap,25",
            "That would exceed the weekly maximum. Current Week: 25/25, Progress: 0/50",
        )
        req.weekly_total = 0
        req.save()
        action.action_points = 30
        action.save()
        old_inform = self.caller.inform
        self.caller.inform = Mock()
        self.call_cmd(
            "/add 1=ap,25",
            "That would exceed the total required. Current Week: 0/25, Progress: 30/50",
        )
        self.call_cmd(
            "/add 1=ap,20",
            "20 ap added. Action #1 Total requirements:\n"
            "military forces: Add some doodz: Fulfilled by: No one yet\n"
            "action points: 50(max per week: 25): Current Week: 20/25, Progress: 50/50",
        )
        self.assertEqual(req.weekly_total, 20)
        self.caller.inform.assert_called_with(
            "A requirement has been completed for Action #1: action points: 50(max per week: 25)",
            append=False,
            category="Actions",
            week=1,
        )
        self.char.pay_money = Mock(return_value=True)
        # check to make sure unmet requirements block submission
        action.requirements.create(
            requirement_type=ActionRequirement.SILVER, total_required_amount=50
        )
        action.org = Organization.objects.create(name="foo")
        action.save()
        self.call_cmd(
            "/submit 1",
            "You have Action Requirements that are not yet satisfied: "
            "military forces: Add some doodz\nRequirement: silver: 50",
        )
        reqs_string = (
            "Action #1 Total requirements:\n"
            "military forces: Add some doodz: Fulfilled by: No one yet\n"
            "action points: 50(max per week: 25): Current Week: 20/25, Progress: 50/50\n"
            "silver: 50: Progress: 50/50"
        )
        self.call_cmd("/add 1=silver,50", "50 silver added. " + reqs_string)
        self.call_cmd(
            "/submit 1",
            "You have Action Requirements that are not yet satisfied: "
            "military forces: Add some doodz",
        )
        # tests
        self.account.pay_resources = Mock(return_value=True)
        for name, rtype in [
            ("military", ActionRequirement.MILITARY),
            ("social", ActionRequirement.SOCIAL),
            ("economic", ActionRequirement.ECONOMIC),
        ]:
            action.requirements.create(requirement_type=rtype, total_required_amount=50)
            reqs_string += f"\n{name} resources: 50: Progress: 50/50"
            self.call_cmd(f"/add 1={name},50", f"50 {name} added. {reqs_string}")
        clue = Clue.objects.create(name="test")
        action.requirements.create(requirement_type=ActionRequirement.CLUE, clue=clue)
        self.call_cmd(f"/add 1=clue,{clue.id}", "No Clue found using '1'.")
        clue.discoveries.create(character=self.roster_entry)
        reqs_string += "\nclue: test: Fulfilled by: Testaccount"
        self.call_cmd(f"/add 1=clue,{clue.id}", f"test clue added. {reqs_string}")
        self.call_cmd(
            "/add 1=army,1", "You have successfully relayed new orders to that army."
        )
        self.call_cmd("/toggletraitor 1", "Traitor is now set to: True")
        self.call_cmd("/toggletraitor 1", "Traitor is now set to: False")
        self.call_cmd(
            "/toggleattend 1", "You are marked as no longer attending the action."
        )
        self.call_cmd(
            "/toggleattend 1",
            "You have marked yourself as physically being present for that action.",
        )
        self.call_cmd("/noscene 1", "Preference for offscreen resolution set to: True")
        self.call_cmd("/noscene 1", "Preference for offscreen resolution set to: False")
        self.call_cmd(
            "/readycheck 1", "The following assistants aren't ready: Testaccount2"
        )
        self.call_cmd(
            "/submit 1",
            "Before submitting this action, make certain that you have invited all players you "
            "wish to help with the action, and add any resources necessary. Any invited players "
            "who have incomplete actions will have their assists deleted.\nThe following "
            "assistants are not ready and will be deleted: Testaccount2\nWhen ready, /submit "
            "the action again.",
        )
        self.caller.inform = old_inform
        self.call_cmd(
            "/submit 1",
            "You have new informs. Use @inform 1 to read them.|You have submitted your action.",
        )
        mock_inform_staff.assert_called_with(
            "Testaccount submitted action #1. {wSummary:{n summary"
        )
        # ensure ActionPerEpisode does not affect org actions
        self.assertFalse(ActionPerEpisode.objects.all().exists())
        self.call_cmd(
            "/makepublic 1",
            "The action must be finished before you can make details of it public.",
        )
        action.status = PlotAction.PUBLISHED
        self.call_cmd(
            "/makepublic 1", "You have gained 2 xp for making your action public."
        )
        self.call_cmd("/makepublic 1", "That action has already been made public.")
        self.call_cmd(
            "/question 1=test question", "You have submitted a question: test question"
        )
        action_2 = self.dompc.actions.create(
            actions="completed storyaction",
            status=PlotAction.PUBLISHED,
            date_submitted=datetime.now(),
        )
        action_2.assisting_actions.create(dompc=self.dompc2)
        action_3 = self.dompc.actions.create(
            actions="another completed storyaction",
            status=PlotAction.PUBLISHED,
            date_submitted=datetime.now(),
        )
        action_3.assisting_actions.create(dompc=self.dompc2)
        draft = self.dompc.actions.create(
            actions="storyaction draft",
            status=PlotAction.DRAFT,
            category=PlotAction.RESEARCH,
            topic="test summary",
            stat_used="stat",
            skill_used="skill",
            org=action.org,
        )
        draft.questions.create(is_intent=True, text="intent")
        self.call_cmd(
            "/invite 4=TestAccount2",
            "All actions must point to a plot.",
        )
        plot = Plot.objects.create(
            name="Super Important PSA", usage=Plot.PERSONAL_STORY
        )
        draft.plot = plot
        draft.save()
        self.call_cmd(
            "/invite 4=TestAccount2",
            "You have invited Testaccount2 to join your action.",
        )
        self.call_cmd(
            "/submit 4",
            f"{action.org} has already taken an action this episode: 1.",
        )
        draft.org = None
        draft.save()
        ActionPerEpisode.objects.create(
            player_account=self.current_account,
            plot_action=action,
            episode=self.episode,
        )
        self.call_cmd(
            "/submit 4",
            "You have already taken an action this episode: 1.",
        )
        self.caller = self.account2
        # unused actions can be used as assists. Try with one slot free to be used as an assist
        self.dompc2.actions.create(
            actions="dompc completed storyaction",
            status=PlotAction.PUBLISHED,
            date_submitted=datetime.now(),
        )
        self.call_cmd(
            "/setaction 4=test assist",
            "Action by Testaccount for Super Important PSA now has your assistance: test assist",
        )
        self.dompc2.actions.create(
            actions="another dompc completed storyaction",
            status=PlotAction.PUBLISHED,
            date_submitted=datetime.now(),
        )
        # now both slots used up
        action_4 = self.dompc.actions.create(
            actions="asdf", status=PlotAction.PUBLISHED, date_submitted=datetime.now()
        )
        action_5 = self.dompc.actions.create(
            actions="asdf", status=PlotAction.PUBLISHED, date_submitted=datetime.now()
        )
        # test making an action free
        action_2.free_action = True
        action_2.save()
        self.call_cmd(
            "/setaction 4=test assist",
            "Action by Testaccount for Super Important PSA now has your assistance: test assist",
        )
        # cancel an action to free a slot
        action_2.status = PlotAction.CANCELLED
        action_2.save()
        self.call_cmd(
            "/setaction 4=test assist",
            "Action by Testaccount for Super Important PSA now has your assistance: test assist",
        )
        action.status = PlotAction.CANCELLED
        action.save()
        action_4.delete()
        action_5.delete()
        # now back to player 1 to see if they can submit after the other actions are gone
        self.caller = self.account
        self.call_cmd(
            "/submit 4",
            "Before submitting this action, make certain that you have invited all players you "
            "wish to help with the action, and add any resources necessary. Any invited players "
            "who have incomplete actions will have their assists deleted.\nThe following "
            "assistants are not ready and will be deleted: Testaccount2\nWhen ready, /submit "
            "the action again.",
        )
        action_4 = self.dompc.actions.last()
        action_4.status = PlotAction.CANCELLED
        action_4.save()
        self.call_cmd(
            "/newaction test crisis=testing",
            "You have drafted a new action (#9) to respond to Test Crisis: "
            "testing|Please note that you cannot invite players to an "
            "action once it is submitted.",
        )
        action_9 = PlotAction.objects.get(id=9)
        date = datetime.now() + timedelta(days=7)
        ServerConfig.objects.conf("end_break_date", date)
        self.call_cmd("/category 9=combat", "category set to Combat.")
        self.call_cmd(
            "/ooc_intent 9=testooc", "You have set your ooc intent to be: testooc"
        )
        self.call_cmd("/tldr 9=summary", "topic set to summary.")
        self.call_cmd(
            "/roll 9=Strength,athletics",
            "stat set to strength.|skill set to athletics.",
        )
        self.call_cmd("/submit 9", "Cannot submit an action while staff are on break.")
        action_9.org = Organization.objects.create(name="foo")
        action_9.save()
        action_9.status = PlotAction.NEEDS_PLAYER
        action_9.save()
        self.call_cmd("/submit 9", "You have submitted your action.")

    @patch("world.stat_checks.models.randint")
    @patch("world.dominion.plots.models.inform_staff")
    @patch("world.dominion.plots.models.get_week")
    def test_cmd_gm_action(self, mock_get_week, mock_inform_staff, mock_randint):
        from datetime import datetime

        now = datetime.now()
        mock_get_week.return_value = 1
        mock_randint.return_value = 0
        plot = Plot.objects.create(name="GM Plot", usage=Plot.GM_PLOT)
        action = self.dompc2.actions.create(
            actions="test",
            status=PlotAction.NEEDS_GM,
            plot=plot,
            editable=False,
            silver=50,
            date_submitted=now,
            topic="test summary",
        )
        action.set_ooc_intent("ooc intent test")
        self.setup_cmd(story_actions.CmdGMAction, self.account)
        self.call_cmd("/story 2=foo", "No action by that ID #.")
        self.call_cmd("/story 1=foo", "story set to foo.")
        self.call_cmd(
            "/tldr 1",
            "Summary of action 1\nAction by Testaccount2 for GM Plot: Summary: test summary",
        )
        self.call_cmd("/secretstory 1=sekritfoo", "secret_story set to sekritfoo.")
        self.call_cmd("/stat 1=charm", "stat set to charm.")
        self.call_cmd("/skill 1=seduction", "skill set to seduction.")
        self.call_cmd("/diff 1=25", "target_rank set to God I.")
        self.call_cmd("/diff 1=hard", "target_rank set to Boss I.")
        self.call_cmd(
            "/assign 1=Testaccount",
            "gm set to Testaccount.|GM for the action set to Testaccount",
        )
        self.call_cmd(
            "/invite 1=TestAccount2", "The owner of an action cannot be an assistant."
        )
        self.call_cmd(
            "/invite 1=TestAccount",
            "You have new informs. Use @inform 1 to read them."
            "|You have invited Testaccount to join your action.",
        )
        # test adding requirements
        self.caller.inform = Mock()
        self.account2.inform = Mock()
        self.call_cmd(
            "/addrequirement/foo 1=bar", "That is not a recognized requirement type."
        )
        self.call_cmd(
            "/addrequirement/resources 1=silver,50000",
            "You have added a requirement: silver: 50000",
        )
        self.account2.inform.assert_called_with(
            "A new requirement has been added to Action #1: silver: 50000\n"
            "For resources, use action/add to contribute the required amounts. For\n"
            "required clues, revelations, items, or magic, have a character who is on\n"
            "the action and has the required entity add its ID as the value. For required\n"
            "event prerequisites, add a plot RFR ID as the value, as well as an\n"
            "explanation for how the plot satisfies the requirement.\n"
            "Once all requirements have been met, the action can be resubmitted for\n"
            "evaluation by GMs.",
            append=False,
            category="Actions",
            week=1,
        )
        self.call_cmd(
            "/addrequirement/clue 1=test clue", "No Clue found using 'test clue'."
        )
        Clue.objects.create(name="test clue")
        Clue.objects.create(name="test clue 2")
        self.call_cmd(
            "/addrequirement/clue 1=test clue",
            "You have added a requirement: clue: test clue",
        )
        self.call_cmd(
            "/addrequirement/clue 1=test clue 2",
            "You have added a requirement: clue: test clue 2",
        )
        self.call_cmd(
            "/addrequirement/revelation 1=test rev",
            "No Revelation found using 'test rev'.",
        )
        Revelation.objects.create(name="test rev")
        self.call_cmd(
            "/addrequirement/revelation 1=test rev",
            "You have added a requirement: revelation: test rev",
        )
        self.call_cmd("/addrequirement/item 1=asdf", "No ObjectDB found using 'asdf'.")
        self.call_cmd(
            "/addrequirement/item 1=Obj2", "You have added a requirement: item: Obj2"
        )
        self.call_cmd(
            "/addrequirement/skillnode 1=test node",
            "No SkillNode found using 'test node'.",
        )
        node = SkillNode.objects.create(name="test node")
        self.call_cmd(
            "/addrequirement/skillnode 1=test node",
            "You have added a requirement: magic skill node: test node",
        )
        self.call_cmd(
            "/addrequirement/spell 1=test spell", "No Spell found using 'test spell'."
        )
        Spell.objects.create(name="test spell", node=node)
        self.call_cmd(
            "/addrequirement/spell 1=test spell",
            "You have added a requirement: spell: test spell",
        )
        self.call_cmd(
            "/addrequirement/event 1=test",
            "You have added a requirement: Other Requirement/Event: test",
        )
        self.call_cmd(
            "/addrequirement/forces 1=test",
            "You have added a requirement: military forces: test",
        )
        self.assertEqual(action.status, action.NEEDS_PLAYER)
        # test asking questions
        action.ask_question("foo inform")
        self.caller.inform.assert_called_with(
            "{cTestaccount2{n added a comment/question about Action #1:\nfoo inform",
            category="Action questions",
        )
        self.call_cmd(
            "/ooc/allowedit 1=Sure go nuts", "editable set to True.|Answer added."
        )
        self.account2.inform.assert_called_with(
            "GM Testaccount has posted a followup to action 1: Sure go nuts",
            append=False,
            category="Actions",
            week=1,
        )
        self.assertEquals(action.editable, True)
        self.call_cmd(
            "/togglefree 1",
            "You have made their action free and the player has been informed.",
        )
        self.account2.inform.assert_called_with(
            "Your action is now a free action and will "
            "not count towards your maximum.",
            append=False,
            category="Actions",
            week=1,
        )
        # test refund
        action.economic = 2000
        action.save()
        self.account2.gain_resources = Mock()
        self.call_cmd("/cancel 1", "Action cancelled.")
        self.account2.gain_resources.assert_called_with("economic", 2000)
        self.assertEquals(self.assetowner2.vault, 50)
        self.assertEquals(action.status, PlotAction.CANCELLED)
        self.call_cmd("/markpending 1", "status set to Pending Resolution.")
        self.assertEquals(action.status, PlotAction.PENDING_PUBLISH)
        self.call_cmd(
            "/check 1", "The new outcome for the action is: simply outclassed"
        )
        self.call_cmd(
            "/publish 1=story test",
            "That story already has an action written. "
            "To prevent accidental overwrites, please change "
            "it manually and then /publish without additional arguments.",
        )
        action.story = ""
        action.ask_question("another test question")
        self.call_cmd("/markanswered 1", "You have marked the questions as answered.")
        self.assertEqual(action.questions.last().mark_answered, True)
        self.call_cmd(
            "1",
            f"Action ID: #1 Category: Unknown  Date: {action.date_submitted.strftime('%x %X')}  GM: Testaccount\n"
            "Action by Testaccount2 for GM Plot\n"
            "Summary: test summary\n"
            "Action: test\n"
            "[physically present] Perception (stat) + Investigation (skill) at target rank Boss I\n"
            "Testaccount2 OOC intentions: ooc intent test\n\n"
            "OOC Notes and GM responses\n"
            "Testaccount2 OOC Question: foo inform\n"
            "Reply by Testaccount: Sure go nuts\n"
            "Testaccount2 OOC Question: another test question\n"
            "Outcome Value: simply outclassed\n"
            "Story Result: \n"
            "Secret Story sekritfoo\n"
            "Total requirements:\n"
            "silver: 50000: Progress: 50/50000\n"
            "clue: test clue: Fulfilled by: No one yet\n"
            "clue: test clue 2: Fulfilled by: No one yet\n"
            "revelation: test rev: Fulfilled by: No one yet\n"
            "item: Obj2: Fulfilled by: No one yet\n"
            "magic skill node: test node: Fulfilled by: No one yet\n"
            "spell: test spell: Fulfilled by: No one yet\n"
            "Other Requirement/Event: test: Fulfilled by: No one yet\n"
            "military forces: test: Fulfilled by: No one yet\n"
            "[STATUS: Pending Resolution]",
        )
        self.call_cmd(
            "/publish 1=story test",
            "You have published the action and sent the players informs.",
        )
        self.assertEquals(action.status, PlotAction.PUBLISHED)
        self.account2.inform.assert_called_with(
            "{wGM Response to action for crisis:{n GM Plot\n"
            "{wCheck Result:{n simply outclassed\n\n"
            "{wStory Result:{n story test\n\n",
            append=False,
            category="Actions",
            week=1,
        )
        mock_inform_staff.assert_called()
        with patch(
            "server.utils.arx_utils.broadcast_msg_and_post"
        ) as mock_msg_and_post:
            from web.character.models import Story, Chapter, Episode

            chapter = Chapter.objects.create(name="test chapter")
            Episode.objects.create(name="test episode", chapter=chapter)
            Story.objects.create(name="test story", current_chapter=chapter)
            self.call_cmd("/gemit 1=test gemit", "StoryEmit created.")
            mock_msg_and_post.assert_called_with(
                "test gemit", self.caller, episode_name="test episode"
            )
            mock_inform_staff.assert_called()


class GeneralTests(TestEquipmentMixins, ArxCommandTest):
    def test_cmd_put(self):
        self.setup_cmd(general.CmdPut, self.char2)
        self.call_cmd("a fox mask", "Usage: put <name> in <name>")
        self.call_cmd(
            "purse1 in purse1", "You can't put an object inside itself.|Nothing moved."
        )
        self.purse1.move_to(self.room1)
        self.purse1.item_data.is_locked = True
        self.call_cmd("a fox mask in purse1", "You'll have to unlock Purse1 first.")
        self.purse1.item_data.is_locked = False
        self.call_cmd("hairpins1 in purse1", "You put Hairpins1 in Purse1.")
        self.mask1.item_data.quality_level = 11
        self.catsuit1.wear(self.char2)
        self.mask1.wear(self.char2)
        self.create_ze_outfit("Bishikiller")
        self.mask1.remove(self.char2)
        self.mask1.item_data.size = 20
        self.purse1.item_data.capacity = 10
        self.call_cmd(
            "/outfit Bishikiller in purse1",
            "Slinkity1 is currently worn and cannot be moved.|"
            "No more room; A Fox Mask won't fit.|"
            "Nothing moved.",
        )
        # currently trying to put away an outfit will remove it
        # but not move if no room. May want to change in future
        self.mask1.wear(self.char2)
        self.purse1.item_data.capacity = 500
        self.mask1.remove(self.char2)
        self.call_cmd(
            "/outfit Bishikiller in purse1",
            "Slinkity1 is currently worn and cannot be moved.|"
            "You put A Fox Mask in Purse1.",
        )
        self.purse1.item_data.is_locked = True
        self.caller = self.char1  # staff
        self.call_cmd("5 silver in purse1", "You do not have enough money.")
        self.char1.db.currency = 30.0
        self.hairpins1.move_to(self.room1)
        self.mask1.move_to(self.room1)
        self.obj1.move_to(self.char1)
        self.call_cmd("5 silver in purse1", "You put 5.0 silver in Purse1.")
        self.assertEqual(self.purse1.db.currency, 5.0)
        self.call_cmd("all in purse1", "You put Obj in Purse1.")
        self.assertEqual(self.char1.db.currency, 25.0)
        self.assertEqual(self.obj1.location, self.purse1)


class OverridesTests(TestEquipmentMixins, ArxCommandTest):
    def test_cmd_get(self):
        self.setup_cmd(overrides.CmdGet, self.char2)
        self.call_cmd("", "What will you get?")
        self.call_cmd("obj", "You get Obj.")
        self.obj1.move_to(self.obj2)
        self.call_cmd("obj from Obj2", "That is not a container.")
        self.purse1.move_to(self.room1)
        self.obj1.move_to(self.purse1)
        self.purse1.item_data.is_locked = True
        self.call_cmd("obj from purse1", "You'll have to unlock Purse1 first.")
        self.purse1.item_data.is_locked = False
        self.call_cmd("all from Purse1", "You get Obj from Purse1.")
        self.call_cmd(
            "5 silver from purse1",
            "Not enough money. You tried to get 5.0, but can only get 0.0.",
        )
        self.purse1.db.currency = 30.0
        self.call_cmd("5 silver from purse1", "You get 5 silver from Purse1.")
        self.assertEqual(self.obj1.location, self.char2)
        self.assertEqual(self.char2.db.currency, 5.0)
        self.assertEqual(self.purse1.db.currency, 25.0)
        self.mask1.item_data.quality_level = 11
        self.catsuit1.wear(self.char2)
        self.mask1.wear(self.char2)
        self.create_ze_outfit("Bishikiller")
        self.mask1.remove(self.char2)
        self.mask1.move_to(self.purse1)
        self.call_cmd(
            "/outfit Bishikiller from purse1", "You get A Fox Mask from Purse1."
        )
        self.purse1.item_data.is_locked = True
        self.caller = self.char1  # staff
        self.call_cmd("5 silver from purse1", "You get 5 silver from Purse1.")

    def test_cmd_inventory(self):
        self.setup_cmd(overrides.CmdInventory, self.char1)
        self.char1.currency = 125446
        self.assetowner.economic = 5446
        self.call_cmd(
            "",
            "You currently have 0 xp and 100 ap.\n"
            "Maximum AP: 300  Weekly AP Gain: 160\n"
            "You are carrying (Volume: 0/100):\n"
            "Money: coins worth a total of 125,446.00 silver pieces\n"
            "Bank Account:           0 silver coins\n"
            "Prestige:               0  Resources         Social Clout: 0\n"
            "|__ Legend:             0  Economic: 5,446\n"
            "|__ Fame:               0  Military:     0\n"
            "|__ Grandeur:           0  Social:       0\n"
            "|__ Propriety:          0\nMaterials:",
        )

    def test_cmd_say(self):
        self.setup_cmd(overrides.CmdArxSay, self.char1)
        self.char2.msg = Mock()
        self.call_cmd("testing", 'You say, "testing"')
        self.char2.msg.assert_called_with(
            from_obj=self.char1,
            text=('Char says, "testing{n"', {}),
            options={"is_pose": True},
        )
        self.caller.db.currently_speaking = "foobar"
        self.call_cmd("testing lang", 'You say in Foobar, "testing lang"')
        self.char2.msg.assert_called_with(
            from_obj=self.char1,
            text=('Char says in Foobar, "testing lang{n"', {}),
            options={
                "language": "foobar",
                "msg_content": "testing lang",
                "is_pose": True,
            },
        )
        self.char1.fakename = "Bob the Faker"
        self.caller.db.currently_speaking = None
        self.call_cmd("test", 'You say, "test"')
        self.char2.msg.assert_called_with(
            from_obj=self.char1,
            text=('Bob the Faker says, "test{n"', {}),
            options={"is_pose": True},
        )
        self.char2.tags.add("story_npc")
        self.call_cmd("test", 'You say, "test"')
        self.char2.msg.assert_called_with(
            'Bob the Faker {c(Char){n says, "test{n"',
            options={"is_pose": True},
            from_obj=self.char1,
        )

    def test_cmd_who(self):
        self.setup_cmd(overrides.CmdWho, self.account2)
        self.call_cmd(
            "asdf",
            "Players:\n\nPlayer name Fealty Idle \n\nShowing 0 out of 1 unique account logged in.",
        )

    def test_cmd_set(self):
        self.setup_cmd(overrides.CmdArxSetAttribute, self.char)
        self.call_cmd(f" here/capacity=200", "Set item data Room/capacity = 200")
        self.assertEqual(self.room.item_data.capacity, 200)
        self.call_cmd(
            f"/char {self.char2}/strength=10", "Set trait Char2/strength = 10"
        )


# noinspection PyUnresolvedReferences
class ExchangesTests(TestEquipmentMixins, ArxCommandTest):
    def test_cmd_trade(self):
        self.setup_cmd(exchanges.CmdTrade, self.char2)
        self.char.msg = Mock()
        head = "[Personal Trade] "
        head2 = "|w[|nPersonal Trade|w]|n "
        fail = "Could not finish the exchange."
        self.call_cmd("", "You are not trading with anyone right now.")
        self.call_cmd("char2", "You cannot trade with Char2.")
        self.call_cmd("top1", "You cannot trade with Top1.")
        self.char1.ndb.personal_trade_in_progress = True
        self.call_cmd("Char", "Char has a trade already in progress.")
        self.char1.msg.assert_called_with(
            f"{head2}Char2 wants to trade, but you have a trade in progress."
        )
        self.char1.ndb.personal_trade_in_progress = None
        self.call_cmd(
            "Char", f"{head}Char2 has initiated a trade with Char. (See 'help trade'.)"
        )
        self.call_cmd("/cancel", f"{head}Your trade has been cancelled.")
        self.assertEqual(self.char2.ndb.personal_trade_in_progress, None)
        self.top2.wear(self.char2)
        self.mask1.item_data.quality_level = 11
        self.mask1.wear(self.char2)
        self.call_cmd(
            "Char",
            f"{head}Someone wearing A Fox Mask has initiated a trade with Char. (See 'help trade'.)",
        )
        self.mask1.remove(self.char2)
        trade = self.char1.ndb.personal_trade_in_progress
        self.assertEqual(trade, self.char2.ndb.personal_trade_in_progress)
        self.call_cmd("/item", "Trade what?")
        self.call_cmd("/item top2", f"{head}Someone wearing A Fox Mask offers Top2.")
        self.char1.msg.assert_called_with(
            f"{head2}Someone wearing A Fox Mask offers Top2."
        )
        self.assertEqual(trade.items[self.char2], [self.top2])
        self.call_cmd(
            "/silver", "Amount must be a positive number that you can afford."
        )
        self.call_cmd(
            "/silver -30", "Amount must be a positive number that you can afford."
        )
        self.call_cmd(
            "/silver 30.99", "Amount must be a positive number that you can afford."
        )
        self.call_cmd(
            "/silver 30", f"{head}Someone wearing A Fox Mask offers 30 silver."
        )
        self.call_cmd(
            "/silver 1",
            "Already offered 30 silver. Cancel trade if amount is incorrect.",
        )
        trade.agreements[self.char1] = True
        self.call_cmd(
            "",
            (
                "**********************************************************************\n"
                "[Personal Trade] Someone wearing A Fox Mask offers 30 silver and:\n"
                " + Top2\n"
                "Char offers no money and no items.\n"
                "Someone wearing A Fox Mask has not yet agreed. Char has agreed. \n"
                "**********************************************************************"
            ),
        )
        self.call_cmd(
            "/agree",
            f"{head}Traders must be in the same location. Agreements have been reset.|{fail}",
        )
        self.assertEqual(trade.agreements[self.char1], False)
        self.mask1.wear(self.char2)
        trade.agreements[self.char1] = True
        self.call_cmd(
            "/agree",
            (
                f"{head}Someone wearing A Fox Mask does not have enough silver to complete the trade. "
                f"Agreements have been reset.|{fail}"
            ),
        )
        self.char2.currency = 30
        trade.agreements[self.char1] = True
        self.call_cmd(
            "/agree",
            (
                f"Top2 is currently worn and cannot be moved.|{head}Someone wearing A Fox Mask "
                f"cannot trade Top2. Agreements have been reset.|{fail}"
            ),
        )
        self.top2.remove(self.char2)
        self.char1.location = self.top1
        trade.agreements[self.char1] = True
        self.call_cmd(
            "/agree",
            f"{head}Traders must be in the same location. Agreements have been reset.|{fail}",
        )
        self.char1.location = self.room1
        self.caller = self.char1
        self.call_cmd("/agree", f"{head}Char has agreed to the trade.")
        self.caller = self.char2
        self.call_cmd("/agree", f"{head}Your exchange is complete!")
        self.assertEqual(self.char1.currency, 30)
        self.assertEqual(self.top2.location, self.char1)
        self.char2.ndb.personal_trade_in_progress = trade
        self.char1.ndb.personal_trade_in_progress = "Pineapple"
        self.call_cmd("/agree", "Invalid trade; cancelling it. Please restart.")
        self.assertEqual(self.char1.ndb.personal_trade_in_progress, "Pineapple")

    def test_cmd_give(self):
        self.setup_cmd(exchanges.CmdGive, self.char2)
        self.call_cmd("top1 to char", "You are not holding Top1.")
        self.top2.wear(self.char2)
        self.call_cmd("top2 to char", "Top2 is currently worn and cannot be moved.")
        self.top2.remove(self.char2)
        self.call_cmd("top2 to char", "You give Top2 to Char.")
        self.assertEqual(self.top2.location, self.char1)
        self.char2.currency = 50
        self.call_cmd("-10 silver to char", "Amount must be positive.")
        self.call_cmd("75 silver to char", "You do not have that much money to give.")
        self.call_cmd(
            "25 silver to char", "You give coins worth 25.0 silver pieces to Char."
        )
        self.assertEqual(self.char1.currency, 25)
        self.assertEqual(self.char2.currency, 25)
        self.assetowner2.economic = 50
        self.call_cmd(
            "/resource economic,60 to TestAccount",
            "You do not have enough economic resources.",
        )
        self.account.inform = Mock()
        self.call_cmd(
            "/resource economic,50 to TestAccount",
            "You give 50 economic resources to Char.",
        )
        self.account.inform.assert_called_with(
            "Char2 has given 50 economic resources to you.", category="Resources"
        )
        self.assertEqual(self.assetowner2.economic, 0)
        self.assertEqual(self.assetowner.economic, 50)


# noinspection PyUnresolvedReferences
class RosterTests(ArxCommandTest):
    def setUp(self):
        """Adds rosters and an announcement board"""
        from web.character.models import Roster
        from typeclasses.bulletin_board.bboard import BBoard
        from evennia.utils.create import create_object

        super(RosterTests, self).setUp()
        self.available_roster = Roster.objects.create(name="Available")
        self.gone_roster = Roster.objects.create(name="Gone")
        self.bboard = create_object(typeclass=BBoard, key="Roster Changes")

    @patch.object(roster, "inform_staff")
    def test_cmd_admin_roster(self, mock_inform_staff):
        from world.dominion.models import Organization

        self.org = Organization.objects.create(name="testorg")
        self.member = self.org.members.create(player=self.dompc2, rank=2)
        self.setup_cmd(roster.CmdAdminRoster, self.account)
        self.bboard.bb_post = Mock()
        self.dompc2.patron = self.dompc
        self.dompc2.save()
        self.call_cmd("/retire char2", "Random password generated for Testaccount2.")
        self.assertEqual(self.roster_entry2.roster, self.available_roster)
        entry = self.roster_entry2
        post = (
            "%s no longer has an active player and is now available for applications."
            % entry.character
        )
        url = "http://play.arxmush.org" + entry.character.get_absolute_url()
        post += "\nCharacter page: %s" % url
        subject = "%s now available" % entry.character
        self.bboard.bb_post.assert_called_with(
            self.caller, post, subject=subject, poster_name="Roster"
        )
        mock_inform_staff.assert_called_with(
            "Testaccount has returned char2 to the Available roster."
        )
        self.assertEqual(self.member.rank, 3)
        self.assertEqual(self.dompc2.patron, None)

    def test_cmd_propriety(self):
        self.setup_cmd(roster.CmdPropriety, self.account)
        self.call_cmd(" nonsense", "There's no propriety known as 'nonsense'.")
        self.call_cmd("", "Title                     Propriety")
        self.caller.execute_cmd("admin_propriety/create Tester=50")
        self.call_cmd(
            "",
            "Title                     Propriety\n"
            "Tester                           50",
        )
        self.caller.execute_cmd("admin_propriety/add Tester=testaccount")
        self.call_cmd("tester", "Individuals with the 'Tester' reputation: Char")
        self.caller.execute_cmd("admin_propriety/remove Tester=testaccount")
        self.caller.execute_cmd("admin_propriety/create Vixen=-3")
        self.call_cmd(
            "vixen", "No one is currently spoken of with the 'Vixen' reputation."
        )


# noinspection PyUnresolvedReferences
class SocialTests(ArxCommandTest):
    def test_cmd_where(self):
        self.setup_cmd(social.CmdWhere, self.account)
        self.call_cmd("/shops", "List of shops:")
        self.room1.tags.add("shop")
        self.room1.db.shopowner = self.char2
        self.call_cmd("/shops", "List of shops:\nRoom: Char2")
        from web.character.models import Roster

        self.roster_entry2.roster = Roster.objects.create(name="Bishis")
        self.call_cmd("/shops/all", "List of shops:\nRoom: Char2 (Inactive)")
        # TODO: create AccountHistory thingies, set a firstimpression for one of the Chars
        # TODO: test /firstimp, /rs, /watch
        self.call_cmd(
            "",
            "Locations of players:\nPlayers who are currently LRP have a + by their name, "
            "and players who are on your watch list have a * by their name.\nRoom: Char, Char2",
        )
        self.char2.fakename = "Kamda"
        self.call_cmd(
            "",
            "Locations of players:\nPlayers who are currently LRP have a + by their name, "
            "and players who are on your watch list have a * by their name.\nRoom: Char",
        )
        self.room1.tags.add("private")
        self.call_cmd("", "No visible characters found.")

    def test_cmd_watch(self):
        self.setup_cmd(social.CmdWatch, self.account)
        max_size = social.CmdWatch.max_watchlist_size
        self.call_cmd("testaccount2", "You start watching Char2.")
        self.assertTrue(self.char2 in self.caller.db.watching)
        self.call_cmd("testaccount2", "You are already watching Char2.")
        self.call_cmd("/hide", "Hiding set to True.")
        self.assertTrue(bool(self.caller.db.hide_from_watch))
        self.call_cmd("/hide", "Hiding set to False.")
        self.assertFalse(bool(self.caller.db.hide_from_watch))
        self.call_cmd("/stop testAccount2", "Stopped watching Char2.")
        self.assertTrue(self.char2 not in self.caller.db.watching)
        for _ in range(max_size):
            self.caller.db.watching.append(self.char2)
        self.call_cmd(
            "testAccount2",
            "You may only have %s characters on your watchlist." % max_size,
        )

    def test_cmd_iamhelping(self):
        from web.character.models import PlayerAccount

        self.setup_cmd(social.CmdIAmHelping, self.account)
        paccount1 = PlayerAccount.objects.create(email="foo@foo.com")
        self.account2.inform = Mock()
        ap_cap = self.roster_entry.max_action_points
        self.call_cmd("", "You have 100 AP remaining.")
        self.call_cmd("testaccount2=30", "You cannot give AP to an alt.")
        self.caller.roster.current_account = paccount1
        self.call_cmd("testaccount2=102", "You do not have enough AP.")
        self.roster_entry2.action_points = 250
        self.roster_entry.action_points = 300
        self.call_cmd("testaccount2=1", "Must transfer at least 3 AP.")
        self.call_cmd("testaccount2=aipl", "AP needs to be a number.")
        self.call_cmd("testaccount2=300", "That would put them over %s AP." % ap_cap)
        inform_msg = "Testaccount has given you 30 AP."
        self.call_cmd(
            "testaccount2=90",
            "You use 90 action points and have 210 remaining this week."
            "|Using 90 of your AP, you have given Testaccount2 30 AP.",
        )
        self.account2.inform.assert_called_with(inform_msg, category=inform_msg)
        self.assertEqual(self.roster_entry2.action_points, 280)
        self.assertEqual(self.roster_entry.action_points, 210)

    def test_cmd_rphooks(self):
        self.setup_cmd(social.CmdRPHooks, self.account)
        self.call_cmd(
            "/add bad: name", "That category name contains invalid characters."
        )
        self.call_cmd("/add catname=desc", "Added rphook tag: catname: desc.")
        self.call_cmd("/remove foo", "No rphook by that category name.")
        self.call_cmd("/remove catname", "Removed.")

    def test_cmd_messenger(self):
        self.setup_cmd(social.CmdMessenger, self.char2)
        self.char1.tags.add("no_messengers")
        self.char2.tags.add("no_messengers")
        self.call_cmd(
            "testaccount=hiya",
            "Char cannot send or receive messengers at the moment."
            "|No valid receivers found.",
        )
        self.char2.tags.remove("no_messengers")
        self.call_cmd(
            "testaccount=hiya",
            "Char cannot send or receive messengers at the moment."
            "|No valid receivers found.",
        )
        self.char1.tags.remove("no_messengers")
        self.call_cmd(
            "testaccount=hiya",
            "You dispatch a messenger to Char with the following message:\n\n'hiya'",
        )

    @patch("world.dominion.models.get_week")
    @patch.object(social, "inform_staff")
    @patch.object(social, "datetime")
    def test_cmd_rpevent(self, mock_datetime, mock_inform_staff, mock_get_week):
        from evennia.utils.create import create_script
        from typeclasses.scripts.event_manager import EventManager
        from world.dominion.models import Organization, AssetOwner

        script = create_script(typeclass=EventManager, key="Event Manager")
        script.post_event = Mock()
        now = datetime.now()
        mock_datetime.strptime = datetime.strptime
        mock_datetime.now = Mock(return_value=now)
        mock_get_week.return_value = 1
        self.setup_cmd(social.CmdCalendar, self.account1)
        self.call_cmd("/submit", "You must /create a form first.")
        self.call_cmd("/create", "You are not currently creating an event.")
        self.call_cmd(
            "/create test_event",
            "Starting project. It will not be saved until you submit it. "
            "Does not persist through logout or server reload.\n"
            "Name: test_event\nMain Host: Testaccount\nPublic: Public\n"
            "Description: None\nDate: None\nLocation: None\nLargesse: Small",
        )
        self.call_cmd(
            "/largesse",
            "Level       Cost   Prestige \n"
            "Small       0      0        "
            "Average     100    10000    "
            "Refined     1000   50000    "
            "Grand       10000  200000   "
            "Extravagant 100000 1000000  "
            "Legendary   500000 4000000",
        )
        self.call_cmd(
            "/desc test description", "Desc of event set to:\ntest description"
        )
        self.call_cmd(
            "/submit",
            "Please correct the following errors:\n"
            "Date: This field is required.\n"
            "Plotroom: You must give either a location or a plot room.\n"
            "Name: test_event\nMain Host: Testaccount\nPublic: Public\n"
            "Description: test description\nDate: None\nLocation: None\nLargesse: Small",
        )
        self.call_cmd(
            "/date 26:35 sdf",
            "Date did not match 'mm/dd/yy hh:mm' format. You entered: 26:35 sdf",
        )
        self.call_cmd("/date 1/1/01 12:35", "You cannot make an event for the past.")
        datestr = now.strftime("%x %X")
        self.call_cmd(
            "/date 12/12/30 12:00",
            (
                "Date set to 12/12/30 12:00:00.|"
                + ("Current time is {} for comparison.|".format(datestr))
                + "Number of events within 2 hours of that date: 0"
            ),
        )
        self.call_cmd(
            "/gm testaccount",
            "Testaccount is now marked as a gm.\n"
            "Reminder: Please only add a GM for an event if it's a "
            "player-run plot. Tagging a social event as a PRP is strictly prohibited. "
            "If you tagged this as a PRP in error, use gm on them again to remove them.",
        )
        self.char1.db.currency = -1.0
        self.call_cmd("/largesse grand", "That requires 10000 to buy. You have -1.0.")
        self.char1.db.currency = 10000
        self.call_cmd("/largesse grand", "Largesse level set to grand for 10000.")
        org = Organization.objects.create(name="test org")
        org.members.create(player=self.dompc2, rank=10)
        self.call_cmd("/invite test org", "Invited test org to attend.")
        self.call_cmd("/invite testaccount2", "Invited Testaccount2 to attend.")
        self.call_cmd("/location here", "Room set to Room.")
        self.call_cmd("/location room2", "Room set to Room2.")
        self.call_cmd("/location", "Room set to Room.")
        self.call_cmd("/private foo", "Private must be set to either 'on' or 'off'.")
        self.call_cmd("/private on", "Event set to: private")
        self.call_cmd("/private off", "Event set to: public")
        self.call_cmd(
            "/submit",
            "You pay 10000 coins for the event.|"
            "New event created: test_event at 12/12/30 12:00:00.",
        )
        self.assertEqual(self.char1.db.currency, 0)
        event = RPEvent.objects.get(name="test_event")
        self.assertTrue(event.gm_event)
        self.assertEqual(org.events.first(), event)
        self.assertEqual(self.dompc2.events.first(), event)
        self.assertEqual(event.location, self.room)
        script.post_event.assert_called_with(event, self.account, event.display())
        mock_inform_staff.assert_called_with(
            "New event created by Testaccount: test_event, "
            "scheduled for 12/12/30 12:00:00."
        )
        self.call_cmd(
            "/create test_event",
            "There is already an event by that name. Choose a different name "
            "or add a number if it's a sequel event.",
        )
        self.call_cmd(
            "/sponsor test org,200=1",
            "You do not have permission to spend funds for test org.",
        )
        org.locks.add("withdraw:rank(10)")
        org.save()
        org.members.create(player=self.dompc, rank=1)
        assets = AssetOwner.objects.create(organization_owner=org)
        self.call_cmd(
            "/sponsor test org,200=1", "test org does not have enough social resources."
        )
        assets.social = 200
        assets.save()
        self.call_cmd(
            "/sponsor test org,200=1",
            "test org is now sponsoring test_event for 200 social resources.",
        )
        self.assertEqual(assets.social, 0)
        self.call_cmd("/uninvite testaccount2=2", "No event found by that number.")
        self.call_cmd("/uninvite testaccount2=1", "Removed Testaccount2's invitation.")
        self.call_cmd("/uninvite testaccount2=1", "They are not invited.")
        self.call_cmd("/invite testaccount2=1", "Invited Testaccount2 to attend.")
        self.call_cmd("/invite testaccount2=1", "They are already invited.")
        self.call_cmd("/uninvite test org=1", "Removed test org's invitation.")
        self.call_cmd("/uninvite test org=1", "That organization is not invited.")
        self.call_cmd(
            "/invite test org=1",
            "test org has new @informs. Use @informs/org test org/1 to read them.|"
            "Invited test org to attend.",
        )
        self.call_cmd("/invite test org=1", "That organization is already invited.")
        self.call_cmd(
            "1",
            "Name: test_event\nHosts: Testaccount\nGMs: Testaccount\nOrgs: test org\nLocation: Room\n"
            "Risk: Normal Risk\nEvent Scale: Grand\nDate: 12/12/30 12:00\nDesc:\ntest description\n"
            "Event Page: http://example.com/dom/cal/detail/1/",
        )
        RPEvent.objects.create(name="public event", public_event=True)
        self.call_cmd(
            "/list",
            "Upcoming events:\n\n"
            "ID Name         Date           Host        Public \n"
            "2  public event No date set    No host     Public "
            "1  test_event   12/12/30 12:00 Testaccount Public",
        )
        self.call_cmd(
            "/mine",
            "Upcoming events:\n\n"
            "ID Name       Date           Host        Public \n"
            "1  test_event 12/12/30 12:00 Testaccount Public",
        )

    @patch("world.dominion.models.get_week")
    @patch("server.utils.arx_utils.get_week")
    @patch.object(social, "do_dice_check")
    def test_cmd_praise(self, mock_dice_check, mock_get_week, mock_dom_get_week):
        from web.character.models import PlayerAccount
        from world.dominion.models import Organization, AssetOwner, RPEvent

        self.roster_entry.current_account = PlayerAccount.objects.create(
            email="asdf@asdf.com"
        )
        self.roster_entry.save()
        self.setup_cmd(social.CmdPraise, self.account)
        mock_get_week.return_value = 1
        mock_dom_get_week.return_value = 1
        self.assertEqual(self.account.get_current_praises_and_condemns().count(), 0)
        self.call_cmd(
            "testaccount2", "You have already used all your praises for the week."
        )
        # property mocks have to be reset at the end, or screws up other tests
        old = type(self.char1).social_clout
        prop_mock = PropertyMock(return_value=10)
        type(self.char1).social_clout = prop_mock
        mock_dice_check.return_value = 50
        self.call_cmd(
            "testaccount2,-2=hi",
            "The number of praises used must be a positive number, "
            "and less than your max praises.",
        )
        self.call_cmd(
            "testaccount2,99=hi",
            "The number of praises used must be a positive number, "
            "and less than your max praises.",
        )
        self.account2.inform = Mock()
        self.call_cmd(
            "/all testaccount2=hi",
            "You use 1 action points and have 99 remaining this week.|"
            "You praise the actions of Testaccount2. You have 0 praises remaining.",
        )
        self.account2.inform.assert_called_with(
            "Testaccount has praised you. Your prestige has been adjusted by 90.",
            append=False,
            category="Praised",
            week=1,
        )
        self.assertEqual(self.assetowner2.fame, 90)
        self.assertEqual(self.account.get_current_praises_and_condemns().count(), 1)
        org = Organization.objects.create(name="test org")
        org.inform = Mock()
        org_assets = AssetOwner.objects.create(organization_owner=org)
        self.call_cmd("/org foo", "No organization by that name.")
        self.call_cmd(
            "/org test org",
            "There is no event going on that has test org as a sponsor.",
        )
        event = RPEvent.objects.create(name="test event", location=self.room)
        self.room.db.current_event = event.id
        event.org_event_participation.create(org=org, social=50)
        prop_mock.return_value = 50
        self.call_cmd(
            "/org test org,40=hi2u",
            "You use 1 action points and have 98 remaining this week.|"
            "You praise the actions of Test org. You have 0 praises remaining.",
        )
        org.inform.assert_called_with(
            "Testaccount has praised you. Your prestige has been adjusted by 10,200.",
            append=False,
            category="Praised",
            week=1,
        )
        self.assertEqual(org_assets.fame, 10200)
        # cleanup property mock
        type(self.char1).social_clout = old

    def test_room_mood(self):
        self.setup_cmd(social.CmdRoomMood, self.char)
        self.call_cmd(
            "this is a test mood",
            "Old mood was: |"
            "(OOC)The scene set/room mood is now set to: this is a test mood",
        )
        self.assertEqual(self.room1.db.room_mood[2], "this is a test mood")
        self.call_cmd("", "Old mood was: this is a test mood|Mood erased.")
        self.assertEqual(self.room1.db.room_mood, None)

    @patch.object(social, "inform_staff")
    def test_cmd_favor(self, mock_inform_staff):
        from world.dominion.models import Organization, AssetOwner

        org = Organization.objects.create(name="testorg", category="asdf")
        org_assets = AssetOwner.objects.create(organization_owner=org)
        self.setup_cmd(social.CmdFavor, self.account2)
        self.call_cmd("", "No organization by the name ''.")
        self.call_cmd("testorg", "Those Favored/Disfavored by testorg")
        self.call_cmd(
            "/add testorg=testaccount", "You do not have permission to set favor."
        )
        org.members.create(player=self.dompc2, rank=1)
        self.call_cmd(
            "/add testorg=testaccount",
            "You must provide a name, target, and gossip string.",
        )
        self.call_cmd("/add testorg=foo,5/bar", "Could not find 'foo'.")
        self.call_cmd(
            "/add testorg=testaccount,5/bar",
            "That would bring your total favor to 5, and you can only spend 0.",
        )
        org.social_influence = 3000
        mem2 = org.members.create(player=self.dompc, rank=4)
        self.call_cmd(
            "/add testorg=testaccount,1/bar", "Cannot set favor for a member."
        )
        org.category = "noble"
        self.call_cmd(
            "/add testorg=testaccount,1/bar",
            "Favor can only be set for vassals or non-members.",
        )
        mem2.rank = 6
        self.call_cmd(
            "/add testorg=testaccount,1/bar",
            "Cost will be 200. Repeat the command to confirm.",
        )
        rep = self.dompc.reputations.get(organization=org)
        rep.affection = 10
        rep.respect = 5
        self.call_cmd(
            "/add testorg=testaccount,1/bar",
            "Cost will be 185. Repeat the command to confirm.",
        )
        self.call_cmd(
            "/add testorg=testaccount,1/bar", "You cannot afford to pay 185 resources."
        )
        self.assetowner2.social = 200
        self.account2.ndb.favor_cost_confirmation = 185
        self.call_cmd(
            "/add testorg=testaccount,1/stuff",
            "Set Testaccount's favor in testorg to 1.",
        )
        mock_inform_staff.assert_called_with(
            "Testaccount2 set gossip for Testaccount's reputation with "
            "testorg to: stuff"
        )
        self.call_cmd(
            "testorg", "Those Favored/Disfavored by testorg\nTestaccount (1): stuff"
        )
        org_assets.fame = 50000
        org_assets.legend = 10000
        org_assets.save()
        self.assertEqual(self.assetowner.propriety, 3000)
        self.assertEqual(self.assetowner.propriety, rep.propriety_amount)
        self.call_cmd("/all", "Characters with favor: Testaccount for testorg (1)")
        self.call_cmd("/remove testorg=testaccount", "Favor for Testaccount removed.")
        self.assertEqual(self.assetowner.propriety, 0)
        self.call_cmd("/all", "Characters with favor: ")


# noinspection PyUnresolvedReferences
class SocialTestsPlus(ArxCommandTest):
    num_additional_characters = 1

    @patch.object(social, "inform_staff")
    def test_cmd_randomscene(self, mock_inform_staff):
        from web.character.models import PlayerAccount

        self.setup_cmd(social.CmdRandomScene, self.char1)
        self.char2.sessions.all = Mock(return_value="Meow")
        self.account2.db_is_connected = True
        self.account2.last_login = datetime.now()
        self.account2.save()
        self.roster_entry2.current_account = PlayerAccount.objects.create(email="foo")
        self.roster_entry2.save()
        temp = social.random.choice
        social.random.choice = Mock(return_value="+plots")
        rptool_str = "\nRandomly chosen Roleplay Tool: +plots"
        self.call_cmd(
            "",
            "@Randomscene Information for this week: \nRandomly generated RP partners: Char2"
            "\nReminder: Please only /claim those you have interacted with significantly in a scene."
            "%s" % rptool_str,
        )
        self.char1.player_ob.db.random_scenelist = [self.char2, self.char2, self.char3]
        self.call_cmd(
            "/online",
            "@Randomscene Information for this week: Only displaying online characters."
            "\nRandomly generated RP partners: Char2 and Char2"
            "\nReminder: Please only /claim those you have interacted with significantly "
            "in a scene.%s" % rptool_str,
        )
        self.call_cmd(
            "/claim Char2",
            "You must include some summary of the scene. It may be quite short.",
        )
        self.call_cmd(
            "/claim Char2=test test test",
            "You have sent Char2 a request to validate your scene: " "test test test",
        )
        mock_inform_staff.assert_called_with(
            "Char has completed this random scene with Char2: test test test"
        )
        self.call_cmd(
            "/claim Char2=test test test",
            "You have already claimed a scene with Char2 this week.",
        )
        self.char2.item_data.false_name = "asdf"
        self.char2.aliases.add("asdf")
        self.caller = self.char3  # mask test, not staff
        self.call_cmd("/claim Char2=meow", "Could not find 'Char2'.")
        self.call_cmd("/claim asdf=meow", "You cannot claim 'asdf'.")
        self.caller = self.char1
        self.call_cmd("/claim Char2=test test test", "You cannot claim 'Char2'.")
        self.call_cmd(
            "",
            "@Randomscene Information for this week: \nRandomly generated RP partners: Char2 and Char3"
            "\nReminder: Please only /claim those you have interacted with significantly in a scene."
            "\nThose you have already RP'd with: Char2%s" % rptool_str,
        )
        self.caller = self.char2
        self.call_cmd(
            "/viewrequests",
            "| Name                               | Summary                               "
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n"
            "| Char                               | test test test",
        )
        self.call_cmd(
            "/validate Tehom",
            "No character by that name has sent you a request.|\n"
            "| Name                               | Summary                               "
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n"
            "| Char                               | test test test",
        )
        self.call_cmd(
            "/validate Char",
            "Validating their scene. Both of you will receive xp for it later.",
        )
        self.assertEqual(self.char2.player_ob.db.validated_list, [self.char1])
        self.char2.player_ob.db.random_scenelist = [self.char3]
        self.call_cmd(
            "/claim char3=testy test",
            "You have sent char3 a request to validate your scene: testy test",
        )
        self.caller = self.char3
        self.char3.db.random_rp_command_this_week = "+plots"
        self.char3.db.rp_command_used = True
        rptool_str += " (Already used)"
        self.call_cmd(
            "/viewrequests",
            "| Name                                | Summary                              "
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n"
            "| asdf                                | testy test",
        )
        self.call_cmd(
            "/validate char2",
            "No character by that name has sent you a request.|\n"
            "| Name                                | Summary                              "
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n"
            "| asdf                                | testy test",
        )
        self.call_cmd(
            "/validate asdf",
            "Validating their scene. Both of you will receive xp for it later.",
        )
        self.call_cmd(
            "",
            "@Randomscene Information for this week: \nRandomly generated RP partners: Char2\n"
            "Reminder: Please only /claim those you have interacted with significantly in a scene.\n"
            "Those you have validated scenes for: asdf%s" % rptool_str,
        )
        social.random.choice = temp


class StaffCommandTests(ArxCommandTest):
    def test_cmd_admin_break(self):
        from server.utils.arx_utils import check_break

        now = datetime.now()
        future = now + timedelta(days=1)
        self.setup_cmd(staff_commands.CmdAdminBreak, self.account)
        self.call_cmd("", "Current end date is: No time set.")
        self.assertFalse(check_break())
        self.call_cmd(
            "asdf",
            "Date did not match 'mm/dd/yy hh:mm' format.|You entered: asdf|"
            "Current end date is: No time set.",
        )
        future_string = future.strftime("%m/%d/%y %H:%M")
        self.call_cmd(
            future_string,
            "Break date updated.|Current end date is: %s." % future_string,
        )
        self.assertTrue(check_break())
        self.call_cmd(
            "/toggle_allow_ocs",
            "Allowing character creation during break has been set to True.",
        )
        self.assertFalse(check_break(checking_character_creation=True))
        self.call_cmd(
            "/toggle_allow_ocs",
            "Allowing character creation during break has been set to False.",
        )
        self.assertTrue(check_break(checking_character_creation=True))
        past = now - timedelta(days=1)
        past_string = past.strftime("%m/%d/%y %H:%M")
        self.call_cmd(
            past_string, "Break date updated.|Current end date is: %s." % past_string
        )
        self.assertFalse(check_break())

    @patch("world.dominion.models.get_week")
    def test_cmd_gemit(self, mock_get_week):
        from world.dominion.models import Organization
        from web.character.models import Story, Episode
        from typeclasses.bulletin_board.bboard import BBoard
        from evennia.utils.create import create_object

        board = create_object(
            BBoard, "test board", locks="read: org(test org);post: org(test org)"
        )
        board.bb_post = Mock()
        mock_get_week.return_value = 1
        Story.objects.create(name="test story")
        Episode.objects.create(name="test episode")
        self.setup_cmd(staff_commands.CmdGemit, self.account)
        org = Organization.objects.create(name="test org", org_board=board)
        org.members.create(player=self.dompc2, rank=1)
        self.dompc2.inform = Mock()
        self.call_cmd("/orgs foo=blah", "No organization named 'foo' was found.")
        self.call_cmd("/orgs test org=blah", "Announcing to test org ...\nblah")
        self.dompc2.inform.assert_called_once()
        self.assertEqual(org.emits.count(), 1)
        board.bb_post.assert_called_with(
            msg="blah",
            poster_name="Story",
            poster_obj=self.account,
            subject="test org Story Update",
        )

    def test_cmd_admin_propriety(self):
        from world.dominion.models import Organization, AssetOwner

        org1 = Organization.objects.create(name="testorg")
        org2 = Organization.objects.create(name="Testorg2")
        AssetOwner.objects.create(organization_owner=org1)
        AssetOwner.objects.create(organization_owner=org2)
        self.setup_cmd(staff_commands.CmdAdminPropriety, self.account)
        self.call_cmd("/create test", "Must provide a value for the tag.")
        self.call_cmd(
            "/create test=50", "Created tag test with a percentage modifier of 50."
        )
        self.call_cmd("/create test=30", "Already a tag by the name test.")
        self.call_cmd("", "Propriety Tags: test(50)")
        self.call_cmd(
            "/add test=testaccount,testaccount2, testorg,testorg2",
            "Added to test: Testaccount, Testaccount2, testorg, Testorg2",
        )
        self.call_cmd(
            "test",
            "Entities with test tag: Testaccount, Testaccount2, testorg, Testorg2",
        )
        self.call_cmd(
            "/remove test=testaccount2,testorg2",
            "Removed from test: Testaccount2, Testorg2",
        )
        self.call_cmd("test", "Entities with test tag: Testaccount, testorg")

    def test_cmd_config(self):
        self.setup_cmd(staff_commands.CmdSetServerConfig, self.account)
        self.call_cmd(
            "asdf",
            "Not a valid key: ap regen, ap transfers disabled, cg bonus skill points, income, "
            "material cost multiplier, motd, new clue ap cost, oc",
        )
        self.call_cmd(
            "income=5",
            "| key                                     | value                            "
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n"
            "| ap regen                                | None                             "
            "| ap transfers disabled                   | None                             "
            "| cg bonus skill points                   | None                             "
            "| income                                  | 5.0                              "
            "| material cost multiplier                | None                             "
            "| motd                                    | None                             "
            "| new clue ap cost                        | None                             "
            "| oc                                      | None                             ",
        )
        self.call_cmd(
            "cg bonus skill points=20",
            "| key                                     | value                            "
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n"
            "| ap regen                                | None                             "
            "| ap transfers disabled                   | None                             "
            "| cg bonus skill points                   | 20                               "
            "| income                                  | 5.0                              "
            "| material cost multiplier                | None                             "
            "| motd                                    | None                             "
            "| new clue ap cost                        | None                             "
            "| oc                                      | None                             ",
        )

    def test_cmd_adjustfame(self):
        self.setup_cmd(staff_commands.CmdAdjustFame, self.account)
        self.call_cmd("bob=3", "Could not find 'bob'.|Check spelling.")
        self.call_cmd(
            "testaccount,testaccount2=3000",
            "Adjusted fame for Testaccount, Testaccount2 by 3000",
        )
        self.call_cmd(
            "testaccount,testaccount2=200",
            "Adjusted legend for Testaccount, Testaccount2 by 200",
            cmdstring="adjustlegend",
        )
        self.call_cmd(
            "testaccount2=1000",
            "Adjusted legend for Testaccount2 by 1000",
            cmdstring="adjustlegend",
        )
        self.call_cmd("testaccount2=1000", "Adjusted fame for Testaccount2 by 1000")
        self.assertEqual(self.assetowner.fame, 3000)
        self.assertEqual(self.assetowner2.fame, 4000)
        self.assertEqual(self.assetowner.legend, 200)
        self.assertEqual(self.assetowner2.legend, 1200)


class StaffCommandTestsPlus(ArxCommandTest):
    num_additional_characters = 1

    def test_cmd_gmnotes(self):
        self.setup_cmd(staff_commands.CmdGMNotes, self.char)
        self.call_cmd("vixen", "No SearchTag found using 'vixen'.")
        self.call_cmd("/create vixen", "Tag created for 'vixen'!")
        self.call_cmd("/create bishi", "Tag created for 'bishi'!")
        self.call_cmd(
            "/create Vixen", "Cannot create; tag already exists: vixen (tag #1)"
        )
        self.call_cmd("", "ALL OF THE TAGS: vixen (#1) and bishi (#2)")
        self.call_cmd("/characters vixen", "No character secrets have the 'vixen' tag.")
        slycloo1 = self.char2.clues.create(
            clue_type=2,
            name="Secret #1 of Slyyyy",
            gm_notes="Sly is incredibly hot and smirkity.",
        )
        slycloo2 = self.char2.clues.create(clue_type=2, name="Secret #2 of Slyyyy")
        self.call_cmd(
            "/tag Slyyyy=vixen",
            "Usage: @gmnotes/tag/<class type> <ID or name>=<tag name>\n"
            "Class types: clue, revelation, plot, action, gemit,"
            " rpevent, flashback, objectdb.",
        )
        self.call_cmd(
            "/tag/clue Galvanion is easy=vixen",
            "No Clue found using 'Galvanion is easy'.",
        )
        galvcloo1 = self.char1.clues.create(
            clue_type=2, name="Secret #1 of Galvanion", tangible_object=self.char
        )
        self.call_cmd(
            "/tag/clue Secret=vixen",
            "More than one Clue found with 'Secret'; be specific.",
        )
        self.call_cmd(
            "/tag/clue Secret #1 of Slyyyy=vixen",
            "Added the 'vixen' tag on clue: Secret #1 of Slyyyy.",
        )
        self.call_cmd(
            "/tag/clue Secret #2 of Slyyyy=vixen",
            "Added the 'vixen' tag on clue: Secret #2 of Slyyyy.",
        )
        self.call_cmd(
            "/tag/clue Secret #1 of Galvanion=bishi",
            "Added the 'bishi' tag on clue: Secret #1 of Galvanion.",
        )
        self.call_cmd("/char vixen", "Characters with a 'vixen' secret: Char2")
        self.call_cmd(
            "/tag/clue/rem Secret #2 of Slyyyy=vixen",
            "Removed the 'vixen' tag on clue: Secret #2 of Slyyyy.",
        )
        self.assertFalse(slycloo2.search_tags.all().exists())
        slyplot1 = Plot.objects.create(
            name="Slypose",
            usage=Plot.PLAYER_RUN_PLOT,
            desc="Sly as a fox.",
            headline="Sly as a fox.",
        )
        slyvolvement1 = slyplot1.dompc_involvement.create(
            dompc=self.char2.dompc, gm_notes="Does a fox flirt in the woods?"
        )
        slyvolvement1.admin_status = slyvolvement1.OWNER
        slyvolvement1.save()
        self.call_cmd(
            "/tag/plot Slypose=vixen", "Added the 'vixen' tag on plot: Slypose."
        )
        glyphcloo1 = self.obj.clues.create(
            clue_type=0,
            name="Glyphed Catsuit",
            gm_notes="Chath pets a slyposed vixen and paints roons on her.",
        )
        glyphcloo1.discoveries.create(
            character=self.roster_entry, message="*wriggle*", discovery_method="trauma"
        )
        self.call_cmd(
            "/tag/clue Catsuit=vixen", "Added the 'vixen' tag on clue: Catsuit."
        )
        vixenrev1 = Revelation.objects.create(
            name="Vixens Are Evil", gm_notes="Hss ss ss"
        )
        vixenrev1.clues_used.create(clue=slycloo1, required_for_revelation=False)
        vixenrev1.clues_used.create(clue=glyphcloo1)
        vixenrev1.discoveries.create(
            character=self.roster_entry, message="*cough*", discovery_method="trauma"
        )
        vixenrev1.discoveries.create(
            character=self.roster_entry2,
            message="*smirk*",
            discovery_method="exploration",
        )
        bishirev1 = Revelation.objects.create(
            name="Bishis Are Hot", gm_notes="Also bishis are easy for smirkity glee."
        )
        self.call_cmd("/rev Bishis Are Hot", "No clues exist for Bishis Are Hot.")
        bishirev1.clues_used.create(clue=galvcloo1, required_for_revelation=False)
        self.call_cmd(
            "/rev",
            "# Revelation      Clu Secrt GM Notes              \n"
            "1 Vixens Are Evil 2   1     Hss ss ss             "
            "2 Bishis Are Hot  1   1     Also bishis are easy+",
        )
        self.call_cmd(
            "/rev Vixens",
            "Vixens Are Evil     About Disco GM Notes              \n"
            "Glyphed Catsuit     lore  1     Chath pets a slypose+ "
            "Secret #1 of Slyyyy Char2 0     Sly is incredibly ho+",
        )
        slyplot1.revelation_involvement.create(
            revelation=vixenrev1, gm_notes="Naturally this applies to Slyyyy."
        )
        slyplot1.revelation_involvement.create(
            revelation=bishirev1, gm_notes="Poor bishis do not stand a chance."
        )
        slyplot1.clue_involvement.create(
            clue=slycloo1,
            access=2,
            gm_notes="Not really a secret that Slyyy is sexy tbh.",
        )
        slyplot1.clue_involvement.create(
            clue=slycloo2,
            access=2,
            gm_notes="All Sly's secrets are related to Slyposing.",
        )
        slyplot1.clue_involvement.create(
            clue=glyphcloo1,
            access=1,
            gm_notes="Slyposing synergizes with glyphed catsuits.",
        )
        self.call_cmd(
            "/plot Slypose",
            "REVELATIONS tied to Slypose:\n"
            "[Vixens Are Evil] Naturally this applies to Slyyyy.\n"
            "[Bishis Are Hot] Poor bishis do not stand a chance.\n"
            "CLUES tied to Slypose: (Grants access, Provides hook, Neutral)\n"
            "[Secret #1 of Slyyyy] (#1) Not really a secret that Slyyy is sexy tbh.\n"
            "[Secret #2 of Slyyyy] (#2) All Sly's secrets are related to Slyposing.\n"
            "[Glyphed Catsuit] (#4) Slyposing synergizes with glyphed catsuits.\n",
        )
        self.call_cmd(
            "/plot",
            "| #   | Plot (owner)           | Summary                                     "
            "~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+\n"
            "| 1   | Slypose (Testaccount2) | Sly as a fox.",
        )
        self.call_cmd(
            "/quick Send Help/test",
            "Created placeholder for 'Send Help' (clue #5). GM Notes: test",
        )
        self.call_cmd(
            "/quick Please=She's evil",
            "Please include Topic and GM notes for your quick clue: "
            "<topic>/<GMnotes>[=<target>]",
        )
        self.call_cmd(
            "/quick Please/She's evil=here",
            "Created placeholder for 'Please' (clue #6). GM Notes: She's evil",
        )
        self.assertEqual(
            [str(ob) for ob in self.roster_entry.clues_written.all()],
            ["PLACEHOLDER by Char: Send Help", "PLACEHOLDER by Char: Please"],
        )
        self.call_cmd(
            "/secret Char2,1=Sly you are evil/hot. Srsly./Do not trust.",
            "[Clue #7] Secret #3 of Char2: Sly you are evil/hot. Srsly.\nGM Notes: Do not trust.\n"
            "Created a secret for Char2 related to revelation #1 'Vixens Are Evil'.",
        )
        slyplot1.resolved = True
        slyplot1.save()
        self.call_cmd(
            "/no_gming",
            "Characters in need. These lists cascade, meaning a name will only appear in "
            "its highest category of need.\nNever in a plot: Char and Char3\n"
            "Only in resolved plots: Char2",
        )
        self.char2.dompc.inform = Mock()
        self.char1.dompc.inform = Mock()
        self.call_cmd(
            "/hook 1,1",
            "Hook failed; one exists between secret 'Secret #1 of Slyyyy' (#1) and "
            "plot 'Slypose' (#1) already.",
        )
        self.call_cmd(
            "/hook 3,1=Bishis are excellent to slypose upon.",
            "Created a plot hook for secret 'Secret #1 of Galvanion' (#3) and plot 'Slypose' (#1). "
            "GM Notes: Bishis are excellent to slypose upon.",
        )
        self.char2.dompc.inform.assert_called_with(
            "Char has had a hook created for the plot Slypose. They can use "
            "plots/findcontact to see the recruiter_story written for any "
            "character marked on your plot as a recruiter or above, which are "
            "intended to as in-character justifications on how they could have "
            "heard your character is involved to arrange a scene. Feel free to "
            "reach out to them first if you like.",
            append=True,
            category="Plot",
        )
        self.char1.dompc.inform.assert_called_with(
            append=True,
            category="Plot Hook",
            message="Your secret 'Secret #1 of Galvanion' (#3) and plot "
            "'Slypose' (#1) are now connected! Use plots/findcontact to "
            "decide how you will approach a contact and get involved.",
        )
        self.call_cmd(
            "vixen",
            "Tagged as 'vixen':\n[Clues] Secret #1 of Slyyyy (#1); Glyphed Catsuit (#4)\n"
            "[Plots] Slypose (#1)",
        )
        self.call_cmd(
            "/delete bishi",
            "Tagged as 'bishi':\n"
            "[Clues] Secret #1 of Galvanion (#3)\n"
            "Repeat command to delete the 'bishi' tag anyway.",
        )
        self.call_cmd("/delete bishi", "Deleting the 'bishi' tag. Poof.")
        self.call_cmd(
            "/viewnotes char2",
            "GM Notes for Char2:\n\nSly is incredibly hot and smirkity.\n\nDo not trust.",
        )
        self.call_cmd("/viewnotes here", "GM Notes for Room:\n\nShe's evil")
        self.call_cmd(
            "/secret Char2,1=Secret without gmnote",
            "[Clue #8] Secret #4 of Char2: Secret without gmnote\n"
            "Created a secret for Char2 related to revelation #1 'Vixens Are Evil'.",
        )


class JobCommandTests(TestTicketMixins, ArxCommandTest):
    @patch.object(jobs, "inform_staff")
    def test_cmd_job(self, mock_inform_staff):
        self.setup_cmd(jobs.CmdJob, self.account)
        self.call_cmd(
            "",
            "Open Tickets:\n\n"
            "# Player       Request              Priority/Q \n"
            "1 TestAccount2 Bishi too easy       3 Bugs     "
            "2 TestAccount2 Let me kill a bishi? 3 Request  "
            "3 TestAccount2 Sly Spareaven?       5 Typo     "
            "4 TestAccount2 Command for licking  4 Code     "
            "5 TestAccount2 Bring Sexy Back      3 PRP      "
            "6 TestAccount2 Poison too hot       1 Bugs",
        )
        # Anything that saves ticket prob needs to be inside context manager, for stupid datetime
        with patch("django.utils.timezone.now", Mock(return_value=self.fake_datetime)):
            self.call_cmd(
                "/move 6",
                "Usage: @job/move <#>=<queue> Queue options: Bugs, Code, PRP, Request, "
                "Story, Typo",
            )
            self.call_cmd(
                "/move 6=code", "Ticket 6 is now in queue Coding Requests/Wishlist."
            )
            self.call_cmd("/priority 6=hella", "Must be a number.")
            self.call_cmd("/priority 6=4", "Ticket new priority is 4.")
            self.call_cmd("/assign 6=hella", "Could not find 'hella'.")
            self.call_cmd("/assign 6=Testaccount", "")
            mock_inform_staff.assert_called_with(
                "|wTestaccount assigned ticket #6 to |cTestaccount|w."
            )
            self.call_cmd("/followup 6", "Usage: @job/followup <#>=<msg>")
            self.call_cmd("/followup 6=No Sly. stop. STOP.", "Followup added.")
            self.call_cmd(
                "/close 6=Perforce it is not feasible to transmogrify the dark princess.",
                "Ticket #6 successfully closed.",
            )
        self.call_cmd(
            "6",
            "\n[Ticket #6] Poison too hot"
            "\nQueue: Coding Requests/Wishlist - Priority 4"
            "\nPlayer: TestAccount2\nLocation: Room (#1)"
            "\nSubmitted: 08/27/78 12:08:00 - Last Update: 08/27/78 12:08:00"
            "\nRequest: Let's make Poison an Iksar. Scaled for his pleasure?"
            "\nFollowup by Testaccount: No Sly. stop. STOP.\nAssigned GM: TestAccount"
            "\nGM Resolution: Perforce it is not feasible to transmogrify the dark princess.",
        )
        self.call_cmd(
            "/delete 7",
            "Cannot delete a storyaction. Please move it to a different queue first.",
        )
        self.call_cmd("/delete 1", "Deleting ticket #1.")
        self.call_cmd(
            "1",
            "Open Tickets:\n\n"
            "# Player       Request              Priority/Q \n"
            "2 TestAccount2 Let me kill a bishi? 3 Request  "
            "3 TestAccount2 Sly Spareaven?       5 Typo     "
            "4 TestAccount2 Command for licking  4 Code     "
            "5 TestAccount2 Bring Sexy Back      3 PRP      "
            "|No ticket found by that number.",
        )
        # ... ^_^ TODO: test the various ways to list tickets: /old, /mine, /all, /moreold, /only, etc

    def test_cmd_request(self):
        self.setup_cmd(jobs.CmdRequest, self.account2)
        with patch("django.utils.timezone.now", Mock(return_value=self.fake_datetime)):
            self.call_cmd(
                "Basic request=Hey bishi can I get 3 minutes of your time?",
                "You have new informs. Use @inform 1 to read them.|"
                "Thank you for submitting a request to the GM staff. Your ticket (#8) "
                "has been added to the queue.",
            )
            self.call_cmd(
                "/followup 8=I'll just wait by your vanity mirror. This is a comfy stool.",
                "Followup added.",
            )
            # confirms followup was added:
            self.call_cmd(
                "8",
                "\n[Ticket #8] Basic request"
                "\nQueue: Request for GM action - Priority 3"
                "\nPlayer: TestAccount2\nLocation: Room (#1)"
                "\nSubmitted: 08/27/78 12:08:00 - Last Update: 08/27/78 12:08:00"
                "\nRequest: Hey bishi can I get 3 minutes of your time?"
                "\nFollowup by Testaccount2: I'll just wait by your vanity mirror. "
                "This is a comfy stool.\nGM Resolution: None",
            )
            self.call_cmd(
                "help it's Khirath!=Ok I'mma have to knife fight a bishi brb.",
                "You have new informs. Use @inform 2 to read them.|"
                "Thank you for submitting a request to the GM staff. Your ticket (#9) "
                "has been added to the queue.",
                cmdstring="+911",
            )
            # confirms "+911" elevates priority to 1:
            self.call_cmd(
                "9",
                "\n[Ticket #9] help it's Khirath!"
                "\nQueue: Request for GM action - Priority 1"
                "\nPlayer: TestAccount2\nLocation: Room (#1)"
                "\nSubmitted: 08/27/78 12:08:00 - Last Update: 08/27/78 12:08:00"
                "\nRequest: Ok I'mma have to knife fight a bishi brb."
                "\nGM Resolution: None",
            )
            self.call_cmd(
                "Khirath strangely resistant to slinky squirms.",
                "You have new informs. Use @inform 3 to read them.|"
                "Thank you for submitting a request to the GM staff. Your ticket (#10) "
                "has been added to the queue.",
                cmdstring="bug",
            )
            # confirms "bug" changes the queue:
            self.call_cmd(
                "10",
                "\n[Ticket #10] Khirath strangely resistant..."
                "\nQueue: Bug reports/Technical issues - Priority 3"
                "\nPlayer: TestAccount2\nLocation: Room (#1)"
                "\nSubmitted: 08/27/78 12:08:00 - Last Update: 08/27/78 12:08:00"
                "\nRequest: Khirath strangely resistant to slinky squirms."
                "\nGM Resolution: None",
            )
            self.call_cmd(
                "Seriously it is Deraven not Spareaven who keeps saying this???",
                "You have new informs. Use @inform 4 to read them.|"
                "Thank you for submitting a request to the GM staff. Your ticket (#11) "
                "has been added to the queue.",
                cmdstring="typo",
            )
            # confirms "typo" changes priority and queue:
            self.call_cmd(
                "11",
                "\n[Ticket #11] Seriously it is Deraven not..."
                "\nQueue: Typos - Priority 5"
                "\nPlayer: TestAccount2\nLocation: Room (#1)"
                "\nSubmitted: 08/27/78 12:08:00 - Last Update: 08/27/78 12:08:00"
                "\nRequest: Seriously it is Deraven not Spareaven who keeps saying this???"
                "\nGM Resolution: None",
            )
            self.call_cmd(
                "/close 11=No longer relevant",
                "You have successfully closed ticket #11.",
            )
            self.call_cmd(
                "11",
                "\n[Ticket #11] Seriously it is Deraven not..."
                "\nQueue: Typos - Priority 5"
                "\nPlayer: TestAccount2\nLocation: Room (#1)"
                "\nSubmitted: 08/27/78 12:08:00 - Last Update: 08/27/78 12:08:00"
                "\nRequest: Seriously it is Deraven not Spareaven who keeps saying this???"
                "\nPlayer Resolution: No longer relevant",
            )
            self.call_cmd(
                "/close 12=I bet this ticket exists",
                "No ticket found by that number.|Closed tickets: 11\n"
                "Open tickets: 1, 2, 3, 4, 5, 6, 8, 9, 10\n"
                "Use +request <#> to view an individual ticket. "
                "Use +request/followup <#>=<comment> to add a comment.",
            )
        self.call_cmd(
            "/followup 11=GRR.", "That ticket is already closed. Please make a new one."
        )
        self.call_cmd(
            "/followup 7=Poison?",
            "No ticket found by that number.|Closed tickets: 11\n"
            "Open tickets: 1, 2, 3, 4, 5, 6, 8, 9, 10\n"
            "Use +request <#> to view an individual ticket. "
            "Use +request/followup <#>=<comment> to add a comment.",
        )
        self.call_cmd(
            "",
            "Closed tickets: 11\nOpen tickets: 1, 2, 3, 4, 5, 6, 8, 9, 10\n"
            "Use +request <#> to view an individual ticket. "
            "Use +request/followup <#>=<comment> to add a comment.",
        )


class XPCommandTests(ArxCommandTest):
    def test_cmd_use_xp(self):
        from evennia.server.models import ServerConfig
        from commands.base_commands.guest import setup_voc
        from world import stats_and_skills

        self.setup_cmd(xp.CmdUseXP, self.char2)
        setup_voc(self.char2, "courtier")
        self.char2.item_data.xp = 0
        self.call_cmd(
            "/spend Teasing",
            "'Teasing' wasn't identified as a stat, ability, or skill.",
        )
        self.call_cmd(
            "/spend Seduction",
            "Unable to raise seduction. The cost is 42, and you have 0 xp.",
        )
        self.char2.traits.adjust_skill("seduction")
        ServerConfig.objects.conf("CHARGEN_BONUS_SKILL_POINTS", 8)
        self.char2.adjust_xp(10)
        self.call_cmd(
            "/spend Seduction",
            "You spend 10 xp and have 0 remaining.|"
            "You have increased your seduction to 5.",
        )
        ServerConfig.objects.conf("CHARGEN_BONUS_SKILL_POINTS", 32)
        self.char2.adjust_xp(1063)
        self.call_cmd(
            "/spend Seduction",
            "You cannot buy a legendary skill while you still have catchup xp remaining.",
        )
        ServerConfig.objects.conf("CHARGEN_BONUS_SKILL_POINTS", 5)
        self.call_cmd(
            "/spend Seduction",
            "You spend 1039 xp and have 24 remaining.|"
            "You have increased your seduction to 6.",
        )
        self.assertEqual(self.char2.traits.get_skill_value("seduction"), 6)
        self.assertEqual(stats_and_skills.get_skill_cost(self.char2, "dodge"), 43)
        self.assertEqual(stats_and_skills.get_skill_cost_increase(self.char2), 1.0775)
        self.char2.db.trainer = self.char1
        self.char1.traits.skills = {"teaching": 5, "dodge": 2}
        self.call_cmd(
            "/spend dodge",
            "You spend 24 xp and have 0 remaining.|You have increased your dodge to 1.",
        )
        # TODO: other switches

    def test_award_xp(self):
        self.setup_cmd(xp.CmdAwardXP, self.account)
        self.call_cmd("testaccount2=asdf", "Invalid syntax: Must have an xp amount.")
        self.char2.item_data.xp = 0
        self.call_cmd("testaccount2=5", "Giving 5 xp to Char2.")
        self.assertEqual(self.char2.item_data.xp, 5)
        self.account2.inform = Mock()
        self.call_cmd(
            "testaccount2=15/hi u r gr8",
            "Giving 15 xp to Char2. Message sent to player: hi u r gr8",
        )
        self.assertEqual(self.char2.item_data.xp, 20)
        self.account2.inform.assert_called_with(
            "You have been awarded 15 xp: hi u r gr8", category="XP"
        )


class HelpCommandTests(ArxCommandTest):
    def test_cmd_help(self):
        from evennia.help.models import HelpEntry
        from evennia.utils.utils import dedent
        from commands.default_cmdsets import CharacterCmdSet
        from world.dominion.plots.plot_commands import CmdPlots

        entry = HelpEntry.objects.create(db_key="test entry")
        entry.tags.add("plots")
        self.setup_cmd(cmd_help.CmdHelp, self.char1)
        expected_return = "Help topic for +plots (aliases: +plot)\n"
        expected_return += dedent(CmdPlots.__doc__.rstrip())
        expected_return += "\n\nRelated help entries: test entry\n\n"
        expected_return += "Suggested: +plots, +plot, @gmplots, support, globalscript"
        self.call_cmd("plots", expected_return, cmdset=CharacterCmdSet())


class AdjustCommandTests(ArxCommandTest):
    def setUp(self):
        super().setUp()

        self.setup_cmd(staff_commands.CmdAdjust, self.account1)

        CraftingMaterialType.objects.create(name="test material")

        self.add_character(3)
        self.add_character(4)
        self.setup_character_and_account(self.char3, self.account3, 3)
        self.setup_character_and_account(self.char4, self.account4, 4)

        self.char2.player.inform = Mock()

    @patch("typeclasses.accounts.Account.gain_materials")
    @patch("typeclasses.accounts.Account.gain_resources")
    def test_adjust_failures(self, mock_res_gain, mock_mat_gain):

        not_found = "Could not find 'foo'.|Failed to adjust: foo."
        self.call_cmd("/material foo=test material,1", not_found)

        # Syntax error
        mat_syntax_error = "Usage: @adjust/material <char1>,<char2>,etc.=<material>,<amount>[/<inform msg>]"
        res_syntax_error = "Usage: @adjust/resource <char1>,<char2>,etc.=<resource>,<amount>[/<inform msg>]"
        self.call_cmd("/material Testaccount2=test material,,5", mat_syntax_error)
        self.call_cmd("/resource Testaccount2=economic..5", res_syntax_error)

        # Value must be a number.
        amt_number = "Amount must be an integer."
        self.call_cmd("/material Testaccount2=test material,q", amt_number)
        self.call_cmd("/resource Testaccount2=economic,q", amt_number)
        self.call_cmd("/silver Testaccount2=q", amt_number)

        # Failed to find material in db.
        material_fail = "Could not find a material with the name 'foo'."
        self.call_cmd("/material Testaccount2=foo,1", material_fail)

        # gain_materials() "failed"
        mock_mat_gain.return_value = False
        mat_adjust_fail = "Failed to adjust: Char2."
        self.call_cmd("/material Testaccount2=test material,1", mat_adjust_fail)

        # Incorrect resource type
        bad_resource = "Explosive is not a valid resource type."
        self.call_cmd("/resource Testaccount2=explosive,1", bad_resource)

        # gain_resource() "failed"
        mock_res_gain.return_value = 0
        res_adjust_fail = (
            "Failed to adjust Char2's economic resources.|Failed to adjust: Char2."
        )
        self.call_cmd("/resource Testaccount2=economic,50", res_adjust_fail)

    def test_adjust_resource(self):
        self.assetowner2.economic = 0

        # Test increase.
        adjust_msg = "Awarded 50 economic resources to: Char2."
        inform_msg = "You have been awarded 50 economic resources."
        self.call_cmd("/resource Testaccount2=economic,50", adjust_msg)
        self.char2.player.inform.assert_called_with(
            inform_msg, category="Resource Adjustment"
        )
        self.assertEqual(self.assetowner2.economic, 50)

        # Test award with message.
        self.call_cmd(
            "/resource Testaccount2=economic,50/Here is 50 resources.",
            f"{adjust_msg}  Message sent to player(s): Here is 50 resources.",
        )
        self.char2.player.inform.assert_called_with(
            f"{inform_msg}%r%rMessage: Here is 50 resources.",
            category="Resource Adjustment",
        )
        self.assertEqual(self.assetowner2.economic, 100)

        # Test reduction failure.
        res_adjust_fail = (
            "Char2 only has 100 economic resources on hand.|Failed to adjust: Char2."
        )
        self.call_cmd("/resource Testaccount2=economic,-150", res_adjust_fail)

        # Test reduction.
        adjust_msg = "Deducted 50 economic resources from: Char2."
        inform_msg = "You have been deducted 50 economic resources."
        self.call_cmd("/resource Testaccount2=economic,-50", adjust_msg)
        self.char2.player.inform.assert_called_with(
            inform_msg, category="Resource Adjustment"
        )
        self.assertEqual(self.assetowner2.economic, 50)

    def test_adjust_material(self):
        # Test increase.
        adjust_msg = "Awarded 50 test material to: Char2."
        inform_msg = "You have been awarded 50 test material."
        self.call_cmd("/material Testaccount2=test material,50", adjust_msg)
        self.char2.player.inform.assert_called_with(
            inform_msg, category="Material Adjustment"
        )

        # Get material and confirm increase.
        mat_type = CraftingMaterialType.objects.get(name__iexact="test material")
        material = self.assetowner2.owned_materials.get(type=mat_type)
        self.assertEqual(material.amount, 50)

        # Test award with message.
        self.call_cmd(
            "/material Testaccount2=test material,50/Here is 50 material.",
            f"{adjust_msg}  Message sent to player(s): Here is 50 material.",
        )
        self.char2.player.inform.assert_called_with(
            f"{inform_msg}%r%rMessage: Here is 50 material.",
            category="Material Adjustment",
        )
        self.assertEqual(material.amount, 100)

        # Test reduction failure.
        mat_adjust_fail = (
            "Char2 only has 100 of test material on hand.|Failed to adjust: Char2."
        )
        self.call_cmd("/material Testaccount2=test material,-150", mat_adjust_fail)

        # Test reduction.
        adjust_msg = "Deducted 50 test material from: Char2."
        inform_msg = "You have been deducted 50 test material."
        self.call_cmd("/material Testaccount2=test material,-50", adjust_msg)
        self.assertEqual(material.amount, 50)
        self.char2.player.inform.assert_called_with(
            inform_msg, category="Material Adjustment"
        )

    def test_adjust_silver(self):
        self.char2.db.currency = 0

        # Test increase.
        adjust_msg = "Awarded 50 silver to: Char2."
        inform_msg = "You have been awarded 50 silver."
        self.call_cmd("/silver Testaccount2=50", adjust_msg)
        self.char2.player.inform.assert_called_with(
            inform_msg, category="Silver Adjustment"
        )

        self.assertEqual(self.char2.db.currency, 50)

        # Test with message this time.
        self.call_cmd(
            "/silver Testaccount2=50/Here is 50 silver.",
            f"{adjust_msg}  Message sent to player(s): Here is 50 silver.",
        )
        self.char2.player.inform.assert_called_with(
            f"{inform_msg}%r%rMessage: Here is 50 silver.",
            category="Silver Adjustment",
        )
        self.assertEqual(self.char2.db.currency, 100)

        # Test reduction failure.
        mny_adjust_fail = "Char2 only has 100 silver on hand.|Failed to adjust: Char2."
        self.call_cmd("/silver Testaccount2=-150", mny_adjust_fail)

        # Test reduction.
        adjust_msg = "Deducted 100 silver from: Char2."
        inform_msg = "You have been deducted 100 silver."
        self.call_cmd("/silver Testaccount2=-100", adjust_msg)
        self.char2.player.inform.assert_called_with(
            inform_msg, category="Silver Adjustment"
        )
        self.assertEqual(self.char2.db.currency, 0)

    def test_adjust_multi(self):
        self.assetowner2.economic = 0
        self.assetowner3.economic = 0
        self.assetowner4.economic = 0

        # Test /resource with multiple characters.
        adjust_msg = "Awarded 50 economic resources to: Char2, Char3, Char4."
        self.call_cmd(
            "/resource Testaccount2,Testaccount3,Testaccount4=economic,50", adjust_msg
        )

        self.assertEqual(self.assetowner2.economic, 50)
        self.assertEqual(self.assetowner3.economic, 50)
        self.assertEqual(self.assetowner4.economic, 50)

        # Test /material with multiple characters.
        adjust_msg = "Awarded 50 test material to: Char2, Char3, Char4."
        self.call_cmd(
            "/material Testaccount2,Testaccount3,Testaccount4=test material,50",
            adjust_msg,
        )

        mat_type = CraftingMaterialType.objects.get(name__iexact="test material")
        mat2 = self.assetowner2.owned_materials.get(type=mat_type)
        mat3 = self.assetowner3.owned_materials.get(type=mat_type)
        mat4 = self.assetowner4.owned_materials.get(type=mat_type)
        self.assertEqual(mat2.amount, 50)
        self.assertEqual(mat3.amount, 50)
        self.assertEqual(mat4.amount, 50)

        # Test /silver with multiple characters.
        self.char2.db.currency = 0
        self.char3.db.currency = 0
        self.char4.db.currency = 0

        adjust_msg = "Awarded 50 silver to: Char2, Char3, Char4."
        self.call_cmd("/silver Testaccount2,Testaccount3,Testaccount4=50", adjust_msg)

        self.assertEqual(self.char2.db.currency, 50)
        self.assertEqual(self.char3.db.currency, 50)
        self.assertEqual(self.char4.db.currency, 50)

        # Test failure with one not-right character.
        result_msg = "Could not find 'foo'.|Awarded 50 silver to: Char2, Char4.|Failed to adjust: foo."
        self.call_cmd("/silver Testaccount2,foo,Testaccount4=50", result_msg)

        self.assertEqual(self.char2.db.currency, 100)
        self.assertEqual(self.char4.db.currency, 100)

        # Test typo with commas in character names.
        result_msg = "Deducted 50 silver from: Char2, Char3, Char4."
        self.call_cmd(
            "/silver Testaccount2,,Testaccount3,,,Testaccount4=-50", result_msg
        )

        self.assertEqual(self.char2.db.currency, 50)
        self.assertEqual(self.char3.db.currency, 0)
        self.assertEqual(self.char4.db.currency, 50)

        # Test more typos with commas in character names.
        result_msg = "Could not find 'Testaccount2.Testaccount3'.|Failed to adjust: Testaccount2.Testaccount3."
        self.call_cmd("/silver Testaccount2.Testaccount3=50", result_msg)
