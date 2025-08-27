import os
from typing import Dict, Optional


class EmoteManager:
    # Base emote definitions with descriptions
    _EMOTE_DEFINITIONS = {
        "Okay": "A simple acknowledgment or agreement",
        "dinkDonk": "An animated attention-grabbing or playful emote",
        "whatDaHell": "Express confusion, disbelief, or bewilderment",
        "sus": "Mark something as suspicious or questionable",
        "JAJAJA": "An animated emote for expressing laughter or amusement",
        "Shrug": "Express uncertainty, indifference, or 'I don't know'",
        "LETSGO": "Show excitement, enthusiasm, or celebration",
        "WICKED": "React to something impressive or awesome",
        "WHAT": "Express surprise, shock, or confusion",
        "Sadge": "Express sadness or disappointment in a relatable way",
        "UltraMad": "Show extreme anger or frustration",
        "WeirdChamp": "React to something strange or awkward",
        "Stonks": "Indicate a successful or profitable situation",
        "SkillIssue": "Point out a mistake or lack of skill",
        "WAYTOOSMART": "React to something clever or insightful",
        "Hypers": "Express excitement or hype",
        "PepoG": "Taking note or learning something new",
        "Awkward": "Express awkwardness or discomfort in a situation",
        "Sure": "Express reluctant agreement, skepticism, or innuendo",
        "IMDEAD": "Express extreme amusement",
        "triangD": "Express excitement or approval with a dance-like emote",
        "um": "Express confusion or hesitation",
        "FeelsWeakMan": "Express feeling weak, sad, or overwhelmed",
        "there": "Pointing out something, or when you've caught someone in a lie"
    }

    def __init__(self):
        # Default emotes that work in all environments
        self._default_emotes = {
            "Okay": "<:Okay:1410039339265691803>"
        }

        # Environment-specific emote IDs
        self._prod_emotes = {
            "dinkDonk": "<a:dinkDonk:1410127578194382940>",
            "whatDaHell": "<:WHATDAHEEEEEEEEELL4x:1410135224154853467>",
            "sus": "<:sus:1410135455067934720>",
            "JAJAJA": "<a:JAJAJAJA:1410136067193180221>",
            "Shrug": "<:Shrug:1410137459374948445>",
            "LETSGO": "<a:LETSGO:1410137887340761129>",
            "WICKED": "<a:WICKED:1410138116467064842>",
            "WHAT": "<a:WHAT:1410138438656720936>",
            "Sadge": "<:Sadge:1410144223461642400>",
            "UltraMad": "<:UltraMad:1410144657186492458>",
            "WeirdChamp": "<a:WeirdChamp:1410144881090756679>",
            "Stonks": "<:STONKS:1410145857805750343>",
            "SkillIssue": "<a:SkillIssue:1410146199348051999>",
            "WAYTOOSMART": "<a:WAYTOOSMART:1410146771711164487>",
            "Hypers": "<:HYPERS:1410147181003800590>",
            "PepoG": "<:PepoG:1410147667937591477>",
            "Awkward": "<a:Awkward:1410147931461521468>",
            "Sure": "<a:Sure:1410148341920043078>",
            "IMDEAD": "<a:IMDEAD:1410148566365769736>",
            "triangD": "<a:triangD:1410149206286667796>",
            "um": "<:um:1410149465599250502>",
            "FeelsWeakMan": "<a:FeelsWeakMan:1410150519661658142>",
            "there": "<:there:1410150978061074442>"
        }

        self._dev_emotes = {
            "dinkDonk": "<a:dinkDonk:1410128777110884413>",
            "whatDaHell": "<:WHATDAHEEEEEEEEELL4x:1410135067748995163>",
            "sus": "<:sus:1410135545455317062>",
            "JAJAJA": "<a:JAJAJAJA:1410135968312328244>",
            "Shrug": "<:Shrug:1410137564802846830>",
            "LETSGO": "<a:LETSGO:1410137785607651338>",
            "WICKED": "<a:WICKED:1410138221857210399>",
            "WHAT": "<a:WHAT:1410138392490151976>",
            "Sadge": "<:Sadge:1410144358325424273>",
            "UltraMad": "<:UltraMad:1410144562265063424>",
            "WeirdChamp": "<a:WeirdChamp:1410144989614182451>",
            "Stonks": "<:STONKS:1410145638196183060>",
            "SkillIssue": "<a:SkillIssue:1410146298253803643>",
            "WAYTOOSMART": "<a:WAYTOOSMART:1410146667432509571>",
            "Hypers": "<:HYPERS:1410147300541468702>",
            "PepoG": "<:PepoG:1410147556645797939>",
            "Awkward": "<a:Awkward:1410148037468098620>",
            "Sure": "<a:Sure:1410148247871164466>",
            "IMDEAD": "<a:IMDEAD:1410148660011860080>",
            "triangD": "<a:triangD:1410149091781902418>",
            "um": "<:um:1410149465599250502>",
            "FeelsWeakMan": "<a:FeelsWeakMan:1410150425696534568>",
            "there": "<:there:1410151071573344286>"
        }

        self._environment = os.getenv("ENVIRONMENT", "development").lower()

    def get_emote(self, name: str) -> Optional[str]:
        """
        Get an emote by name, considering the current environment.
        Case-insensitive lookup with exact match fallback.
        
        Args:
            name: The name of the emote to retrieve
            
        Returns:
            The emote string if found, None otherwise
        """
        # First try exact match in default emotes
        if name in self._default_emotes:
            return self._default_emotes[name]
            
        # Then try exact match in environment emotes
        env_emotes = self._prod_emotes if self._environment == "production" else self._dev_emotes
        if name in env_emotes:
            return env_emotes[name]
            
        # If no exact match, try case-insensitive match
        name_lower = name.lower()
        # Check default emotes
        for emote_name, emote_id in self._default_emotes.items():
            if emote_name.lower() == name_lower:
                return emote_id
                
        # Check environment emotes
        for emote_name, emote_id in env_emotes.items():
            if emote_name.lower() == name_lower:
                return emote_id
        
        return None

    def get_all_emotes(self) -> Dict[str, Dict[str, str]]:
        """
        Get all available emotes for the current environment.
        
        Returns:
            Dictionary containing all available emotes with their IDs and descriptions
        """
        result = {}
        env_emotes = self._prod_emotes if self._environment == "production" else self._dev_emotes
        
        # Add default emotes with descriptions
        for name, emote_id in self._default_emotes.items():
            if name in self._EMOTE_DEFINITIONS:
                result[name] = {
                    "id": emote_id,
                    "description": self._EMOTE_DEFINITIONS[name]
                }
        
        # Add environment-specific emotes with descriptions
        for name, emote_id in env_emotes.items():
            if name in self._EMOTE_DEFINITIONS:
                result[name] = {
                    "id": emote_id,
                    "description": self._EMOTE_DEFINITIONS[name]
                }
        
        return result

# Create a singleton instance
emotes = EmoteManager()

# Usage example:
# from src.utils.emotes import emotes
# some_emote = emotes.get_emote("thumbsup")  # Returns 👍
# custom_emote = emotes.get_emote("pepeLaugh")  # Returns environment-specific Discord emote if configured
