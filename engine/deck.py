"""
Card and Deck primitives for Texas Hold'em.

Cards are immutable value objects identified by rank (2-14) and suit (0-3).
Deck is a standard 52-card deck with shuffle, draw, and burn operations.
"""

from __future__ import annotations
import random
from enum import IntEnum
from typing import List, Optional, Tuple


class Suit(IntEnum):
    """Card suits ordered for display: clubs, diamonds, hearts, spades."""
    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3


# Display symbols and names
SUIT_SYMBOLS = {
    Suit.CLUBS: "♣",
    Suit.DIAMONDS: "♦",
    Suit.HEARTS: "♥",
    Suit.SPADES: "♠",
}

SUIT_NAMES = {
    Suit.CLUBS: "Clubs",
    Suit.DIAMONDS: "Diamonds",
    Suit.HEARTS: "Hearts",
    Suit.SPADES: "Spades",
}

# Ranks: 2=2, ..., 10=10, J=11, Q=12, K=13, A=14
RANK_NAMES = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
    9: "9", 10: "10", 11: "Jack", 12: "Queen", 13: "King", 14: "Ace",
}

RANK_SHORT = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
    9: "9", 10: "T", 11: "J", 12: "Q", 13: "K", 14: "A",
}

# For UI display — shows "10" instead of "T"
RANK_DISPLAY = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
    9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A",
}

# Reverse lookup: short string -> rank int
SHORT_TO_RANK = {v: k for k, v in RANK_SHORT.items()}

# Reverse lookup: symbol -> Suit
SYMBOL_TO_SUIT = {v: k for k, v in SUIT_SYMBOLS.items()}
# Also support lowercase letters
LETTER_TO_SUIT = {"c": Suit.CLUBS, "d": Suit.DIAMONDS, "h": Suit.HEARTS, "s": Suit.SPADES}


class Card:
    """
    Immutable playing card.
    
    rank: int 2-14 (2-10, J=11, Q=12, K=13, A=14)
    suit: Suit enum (CLUBS=0, DIAMONDS=1, HEARTS=2, SPADES=3)
    
    Cards are hashable and comparable by rank (suit breaks ties for sorting only,
    not for poker hand comparison).
    """
    __slots__ = ("rank", "suit", "_hash")

    def __init__(self, rank: int, suit: Suit):
        if not (2 <= rank <= 14):
            raise ValueError(f"Rank must be 2-14, got {rank}")
        if not isinstance(suit, Suit):
            suit = Suit(suit)
        object.__setattr__(self, "rank", rank)
        object.__setattr__(self, "suit", suit)
        object.__setattr__(self, "_hash", hash((rank, suit)))

    def __setattr__(self, name, value):
        raise AttributeError("Card is immutable")

    def __delattr__(self, name):
        raise AttributeError("Card is immutable")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        return self.rank == other.rank and self.suit == other.suit

    def __hash__(self) -> int:
        return self._hash

    def __lt__(self, other: Card) -> bool:
        """Sort by rank descending, then suit. Used for display ordering."""
        if self.rank != other.rank:
            return self.rank < other.rank
        return self.suit < other.suit

    def __repr__(self) -> str:
        return f"Card({RANK_SHORT[self.rank]}{SUIT_SYMBOLS[self.suit]})"

    def __str__(self) -> str:
        return f"{RANK_SHORT[self.rank]}{SUIT_SYMBOLS[self.suit]}"

    @property
    def short(self) -> str:
        """Short string like 'As', 'Th', '2c' for serialization."""
        suit_letter = {Suit.CLUBS: "c", Suit.DIAMONDS: "d", Suit.HEARTS: "h", Suit.SPADES: "s"}
        return f"{RANK_SHORT[self.rank]}{suit_letter[self.suit]}"

    @property
    def rank_name(self) -> str:
        return RANK_NAMES[self.rank]

    @property
    def suit_name(self) -> str:
        return SUIT_NAMES[self.suit]

    @property
    def suit_symbol(self) -> str:
        return SUIT_SYMBOLS[self.suit]

    @property
    def is_red(self) -> bool:
        """Hearts and diamonds are red suits."""
        return self.suit in (Suit.HEARTS, Suit.DIAMONDS)

    def to_dict(self) -> dict:
        """Serialize for JSON API responses."""
        return {
            "rank": self.rank,
            "suit": int(self.suit),
            "rank_short": RANK_SHORT[self.rank],
            "rank_display": RANK_DISPLAY[self.rank],
            "suit_symbol": SUIT_SYMBOLS[self.suit],
            "short": self.short,
            "display": f"{RANK_DISPLAY[self.rank]}{SUIT_SYMBOLS[self.suit]}",
            "is_red": self.is_red,
        }

    @staticmethod
    def from_short(s: str) -> Card:
        """
        Parse a card from short notation: 'As', 'Th', '2c', etc.
        Also accepts symbol notation: 'A♠', 'T♥'.
        """
        if len(s) < 2:
            raise ValueError(f"Invalid card string: '{s}'")
        rank_char = s[0].upper()
        suit_char = s[1:]
        if rank_char not in SHORT_TO_RANK:
            raise ValueError(f"Invalid rank: '{rank_char}'")
        rank = SHORT_TO_RANK[rank_char]
        # Try letter first, then symbol
        suit_lower = suit_char.lower()
        if suit_lower in LETTER_TO_SUIT:
            suit = LETTER_TO_SUIT[suit_lower]
        elif suit_char in SYMBOL_TO_SUIT:
            suit = SYMBOL_TO_SUIT[suit_char]
        else:
            raise ValueError(f"Invalid suit: '{suit_char}'")
        return Card(rank, suit)


def make_card(rank_suit: str) -> Card:
    """Convenience alias for Card.from_short."""
    return Card.from_short(rank_suit)


class Deck:
    """
    Standard 52-card deck with shuffle, draw, and burn operations.
    
    Maintains a list of remaining cards and a list of burned cards.
    Supports removing specific cards (for manual deal / cheat mode).
    """

    def __init__(self, shuffle: bool = True, seed: Optional[int] = None):
        """Create a fresh 52-card deck, optionally shuffled."""
        self._cards: List[Card] = []
        self._burned: List[Card] = []
        self._dealt: List[Card] = []
        self._rng = random.Random(seed)
        self.reset(shuffle)

    def reset(self, shuffle: bool = True) -> None:
        """Reset deck to full 52 cards."""
        self._cards = [
            Card(rank, Suit(suit))
            for suit in range(4)
            for rank in range(2, 15)
        ]
        self._burned = []
        self._dealt = []
        if shuffle:
            self._rng.shuffle(self._cards)

    @property
    def remaining(self) -> int:
        """Number of cards left in the deck."""
        return len(self._cards)

    @property
    def burned(self) -> List[Card]:
        """Cards that have been burned (read-only copy)."""
        return list(self._burned)

    @property
    def dealt(self) -> List[Card]:
        """Cards that have been dealt (read-only copy)."""
        return list(self._dealt)

    def draw(self, count: int = 1) -> List[Card]:
        """
        Draw cards from the top of the deck.
        
        Returns a list of Card objects. Raises if not enough cards remain.
        """
        if count > len(self._cards):
            raise ValueError(f"Cannot draw {count} cards, only {len(self._cards)} remain")
        drawn = self._cards[:count]
        self._cards = self._cards[count:]
        self._dealt.extend(drawn)
        return drawn

    def draw_one(self) -> Card:
        """Draw a single card. Convenience method."""
        return self.draw(1)[0]

    def burn(self) -> Card:
        """Burn one card from the top of the deck."""
        if not self._cards:
            raise ValueError("Cannot burn: deck is empty")
        card = self._cards.pop(0)
        self._burned.append(card)
        return card

    def remove(self, card: Card) -> bool:
        """
        Remove a specific card from the deck (for manual deal mode).
        Returns True if found and removed, False if not in deck.
        """
        try:
            self._cards.remove(card)
            self._dealt.append(card)
            return True
        except ValueError:
            return False

    def remove_cards(self, cards: List[Card]) -> List[Card]:
        """
        Remove specific cards from deck. Returns list of cards that
        were not found (already dealt or burned).
        """
        not_found = []
        for card in cards:
            if not self.remove(card):
                not_found.append(card)
        return not_found

    def peek(self, count: int = 1) -> List[Card]:
        """Look at the top N cards without removing them."""
        return self._cards[:count]

    def is_available(self, card: Card) -> bool:
        """Check if a card is still in the deck."""
        return card in self._cards

    def available_cards(self) -> List[Card]:
        """Return all cards still in the deck (copy)."""
        return list(self._cards)

    def __len__(self) -> int:
        return len(self._cards)

    def __repr__(self) -> str:
        return f"Deck({len(self._cards)} remaining, {len(self._burned)} burned, {len(self._dealt)} dealt)"
