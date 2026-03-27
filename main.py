import array
import asyncio
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pygame

IS_WEB = sys.platform == "emscripten"


class _NoSound:
    """Silent stub so sfx["any"].play() works without errors on web."""
    def play(self, *a, **kw) -> None: pass
    def stop(self, *a, **kw) -> None: pass
    def set_volume(self, *a, **kw) -> None: pass


class _SilentDict(dict):
    def __missing__(self, key: str) -> _NoSound:
        return _NoSound()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 900, 520
GROUND_Y = HEIGHT - 100
FPS = 60
SAMPLE_RATE = 22050
OBSTACLES_PER_LEVEL = 6
SAVE_FILE = Path(__file__).parent / "save_data.json"

# Colors
SKY = (186, 228, 255)
GROUND_COL = (119, 183, 97)
DARK_GROUND = (95, 160, 75)
OBSTACLE_COL = (125, 98, 68)
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
GOLD = (255, 215, 0)
GOLD_DARK = (218, 165, 32)
SPARKLE_COL = (255, 255, 200)
MOUSE_BODY = (180, 180, 180)
MOUSE_EAR = (255, 180, 180)
MOUSE_DARK = (120, 120, 120)
TITLE_COL = (90, 60, 30)
HEART_COL = (255, 80, 90)
PLATFORM_COL = (140, 110, 70)
PLATFORM_TOP = (100, 170, 80)
SHIELD_COL = (100, 180, 255)
MAGNET_COL = (255, 80, 80)
SPEED_COL = (255, 220, 50)
FAR_HILL = (160, 210, 145)
MID_TREE = (90, 160, 70)
TRUNK_COL = (120, 85, 50)
BUSH_COL = (75, 145, 60)
SPIKE_COL = (160, 160, 165)
BIRD_COL = (60, 60, 75)

# Obstacle kinds
OBS_BLOCK = 0
OBS_SPIKE = 1
OBS_BUSH = 2
OBS_BIRD = 3

# Skin definitions: id -> colors + cost
SKINS: dict[str, dict] = {
    "orange": {
        "fur": (245, 166, 75), "fur_dark": (210, 140, 60),
        "belly": (255, 230, 200), "ear_inner": (255, 160, 160),
        "nose": (255, 120, 130), "eyes": (100, 190, 80),
        "cost": 0, "name": "Orange Tabby",
    },
    "gray": {
        "fur": (160, 160, 170), "fur_dark": (120, 120, 130),
        "belly": (210, 210, 220), "ear_inner": (200, 160, 170),
        "nose": (200, 130, 140), "eyes": (80, 160, 200),
        "cost": 10, "name": "Silver",
    },
    "white": {
        "fur": (240, 240, 245), "fur_dark": (200, 200, 210),
        "belly": (255, 255, 255), "ear_inner": (255, 180, 190),
        "nose": (255, 150, 160), "eyes": (100, 150, 220),
        "cost": 15, "name": "Snowball",
    },
    "black": {
        "fur": (50, 50, 55), "fur_dark": (30, 30, 35),
        "belly": (80, 80, 90), "ear_inner": (150, 100, 110),
        "nose": (100, 70, 80), "eyes": (220, 180, 40),
        "cost": 20, "name": "Shadow",
    },
    "calico": {
        "fur": (240, 180, 100), "fur_dark": (80, 60, 40),
        "belly": (255, 240, 220), "ear_inner": (255, 160, 160),
        "nose": (255, 120, 130), "eyes": (140, 200, 80),
        "cost": 25, "name": "Calico",
    },
}
SKIN_ORDER = ["orange", "gray", "white", "black", "calico"]

# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

def load_save() -> dict:
    defaults = {
        "best_score": 0,
        "total_mice": 0,
        "unlocked_skins": ["orange"],
        "selected_skin": "orange",
    }
    if SAVE_FILE.exists():
        try:
            data = json.loads(SAVE_FILE.read_text())
            for k, v in defaults.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return defaults


def write_save(data: dict) -> None:
    try:
        SAVE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Cat
# ---------------------------------------------------------------------------

@dataclass
class Cat:
    x: float = 120.0
    y: float = float(GROUND_Y - 56)
    w: int = 56
    h: int = 56
    vx: float = 0.0
    vy: float = 0.0
    base_speed: float = 4.0
    gravity: float = 0.45
    jump_strength: float = -10.5
    on_ground: bool = True
    facing_right: bool = True
    jumps_left: int = 2
    max_jumps: int = 2
    # Lives & invincibility
    lives: int = 3
    invincible_timer: float = 0.0
    # Power-up state
    shield: bool = False
    magnet_timer: float = 0.0
    speed_boost_timer: float = 0.0
    # Animation
    leg_phase: float = 0.0
    spin_timer: float = 0.0
    # Skin
    skin: str = "orange"

    @property
    def speed(self) -> float:
        return self.base_speed * (1.6 if self.speed_boost_timer > 0 else 1.0)

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, move_left: bool, move_right: bool, jump: bool,
               platforms: list, dt: float) -> None:
        self.vx = 0
        if move_left:
            self.vx = -self.speed
            self.facing_right = False
        if move_right:
            self.vx = self.speed
            self.facing_right = True

        if jump and self.jumps_left > 0:
            self.vy = self.jump_strength
            self.on_ground = False
            self.jumps_left -= 1

        prev_bottom = self.y + self.h

        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy

        if self.x < 0:
            self.x = 0
        if self.x + self.w > WIDTH:
            self.x = WIDTH - self.w

        # Ground
        self.on_ground = False
        floor_y = GROUND_Y - self.h
        if self.y >= floor_y:
            self.y = floor_y
            self.vy = 0
            self.on_ground = True
            self.jumps_left = self.max_jumps

        # One-way platform collision (only when falling)
        if not self.on_ground and self.vy >= 0:
            for plat in platforms:
                pr = plat.rect()
                cat_bottom = self.y + self.h
                if (prev_bottom <= pr.y + 3
                        and cat_bottom >= pr.y
                        and self.x + self.w - 6 > pr.x
                        and self.x + 6 < pr.x + pr.w):
                    self.y = pr.y - self.h
                    self.vy = 0
                    self.on_ground = True
                    self.jumps_left = self.max_jumps
                    break

        # Timers
        if self.invincible_timer > 0:
            self.invincible_timer = max(0, self.invincible_timer - dt)
        if self.magnet_timer > 0:
            self.magnet_timer = max(0, self.magnet_timer - dt)
        if self.speed_boost_timer > 0:
            self.speed_boost_timer = max(0, self.speed_boost_timer - dt)
        if self.spin_timer > 0:
            self.spin_timer = max(0, self.spin_timer - dt)

        # Running animation
        if self.on_ground and abs(self.vx) > 0.1:
            self.leg_phase += 0.35
        else:
            self.leg_phase = 0

    def draw(self, surface: pygame.Surface, tick: int = 0) -> None:
        # Invincibility flash
        if self.invincible_timer > 0 and (tick // 4) % 2 == 0:
            return

        sk = SKINS.get(self.skin, SKINS["orange"])
        fur = sk["fur"]
        fur_dark = sk["fur_dark"]
        belly = sk["belly"]
        ear_inner = sk["ear_inner"]
        nose_col = sk["nose"]
        eye_col = sk["eyes"]

        bx, by = int(self.x), int(self.y)
        flip = not self.facing_right

        # Tail
        if flip:
            pts = [(bx + self.w + 2, by + 30), (bx + self.w + 14, by + 12),
                   (bx + self.w + 8, by + 34), (bx + self.w + 18, by + 28)]
        else:
            pts = [(bx - 2, by + 30), (bx - 14, by + 12),
                   (bx - 8, by + 34), (bx - 18, by + 28)]
        pygame.draw.lines(surface, fur_dark, False, pts, 3)

        # Body
        body_rect = pygame.Rect(bx + 4, by + 20, self.w - 8, self.h - 20)
        pygame.draw.ellipse(surface, fur, body_rect)
        belly_rect = pygame.Rect(bx + 12, by + 28, self.w - 24, self.h - 30)
        pygame.draw.ellipse(surface, belly, belly_rect)

        # Legs (animated)
        leg_y = by + self.h - 10
        if self.on_ground and abs(self.vx) > 0.1:
            off = math.sin(self.leg_phase) * 5
            pygame.draw.ellipse(surface, fur_dark, (bx + 8, leg_y + off, 12, 10))
            pygame.draw.ellipse(surface, fur_dark, (bx + self.w - 20, leg_y - off, 12, 10))
        elif not self.on_ground:
            pygame.draw.ellipse(surface, fur_dark, (bx + 10, leg_y - 4, 10, 8))
            pygame.draw.ellipse(surface, fur_dark, (bx + self.w - 20, leg_y - 4, 10, 8))
        else:
            pygame.draw.ellipse(surface, fur_dark, (bx + 8, leg_y, 12, 10))
            pygame.draw.ellipse(surface, fur_dark, (bx + self.w - 20, leg_y, 12, 10))

        # Head
        head_cx = bx + self.w // 2
        head_cy = by + 16
        pygame.draw.circle(surface, fur, (head_cx, head_cy), 17)

        # Ears
        for side in (-1, 1):
            cx = head_cx + side * 8
            pygame.draw.polygon(surface, fur, [
                (cx - 6, head_cy - 8), (cx, head_cy - 26), (cx + 6, head_cy - 8)])
            pygame.draw.polygon(surface, ear_inner, [
                (cx - 4, head_cy - 9), (cx, head_cy - 22), (cx + 4, head_cy - 9)])

        # Muzzle
        pygame.draw.ellipse(surface, belly, (head_cx - 7, head_cy + 2, 14, 10))

        # Eyes
        blink = (tick % 180) < 6
        le_x = head_cx + (7 if flip else -7)
        re_x = head_cx + (-7 if flip else 7)
        if blink:
            pygame.draw.line(surface, BLACK, (le_x - 3, head_cy - 1), (le_x + 3, head_cy - 1), 2)
            pygame.draw.line(surface, BLACK, (re_x - 3, head_cy - 1), (re_x + 3, head_cy - 1), 2)
        else:
            for ex in (le_x, re_x):
                pygame.draw.ellipse(surface, eye_col, (ex - 4, head_cy - 5, 8, 10))
                pygame.draw.ellipse(surface, BLACK, (ex - 1, head_cy - 4, 3, 8))
                pygame.draw.circle(surface, WHITE, (ex - 1, head_cy - 3), 1)

        # Nose
        pygame.draw.polygon(surface, nose_col, [
            (head_cx, head_cy + 4), (head_cx - 3, head_cy + 1), (head_cx + 3, head_cy + 1)])

        # Mouth
        pygame.draw.arc(surface, fur_dark, (head_cx - 5, head_cy + 4, 5, 4), 3.6, 5.8, 1)
        pygame.draw.arc(surface, fur_dark, (head_cx, head_cy + 4, 5, 4), 3.6, 5.8, 1)

        # Whiskers
        w_dir = 1 if not flip else -1
        for dy in (-2, 1, 4):
            pygame.draw.line(surface, fur_dark,
                             (head_cx + 8 * w_dir, head_cy + 5 + dy),
                             (head_cx + 22 * w_dir, head_cy + 3 + dy), 1)
            pygame.draw.line(surface, fur_dark,
                             (head_cx - 8 * w_dir, head_cy + 5 + dy),
                             (head_cx - 22 * w_dir, head_cy + 3 + dy), 1)

        # Forehead stripes
        for sx in (-4, 0, 4):
            pygame.draw.line(surface, fur_dark,
                             (head_cx + sx, head_cy - 10),
                             (head_cx + sx, head_cy - 5), 1)

        # Double-jump spin effect
        if self.spin_timer > 0:
            r = 28 * (self.spin_timer / 0.4)
            for a_off in range(0, 360, 60):
                angle = math.radians(a_off + tick * 18)
                sx = head_cx + math.cos(angle) * r
                sy = head_cy + math.sin(angle) * r
                pygame.draw.circle(surface, WHITE, (int(sx), int(sy)), 2)

        # Shield bubble
        if self.shield:
            shield_surf = pygame.Surface((self.w + 20, self.h + 20), pygame.SRCALPHA)
            pygame.draw.ellipse(shield_surf, (*SHIELD_COL, 60),
                                (0, 0, self.w + 20, self.h + 20))
            pygame.draw.ellipse(shield_surf, (*SHIELD_COL, 120),
                                (0, 0, self.w + 20, self.h + 20), 2)
            surface.blit(shield_surf, (bx - 10, by - 10))

        # Speed boost trail
        if self.speed_boost_timer > 0:
            trail_x = bx + self.w + 4 if flip else bx - 12
            for i in range(3):
                ty = by + 18 + i * 12
                length = random.randint(6, 14)
                dx = length if flip else -length
                pygame.draw.line(surface, SPEED_COL, (trail_x, ty), (trail_x + dx, ty), 2)

# ---------------------------------------------------------------------------
# Obstacle (multiple types)
# ---------------------------------------------------------------------------

@dataclass
class Obstacle:
    x: float
    y: float
    w: int
    h: int
    speed: float
    kind: int = OBS_BLOCK
    scored: bool = False
    _phase: float = field(default_factory=lambda: random.uniform(0, math.tau))
    _base_y: float = 0.0

    def __post_init__(self) -> None:
        if self.kind == OBS_BIRD:
            self._base_y = self.y

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, tick: int) -> None:
        self.x -= self.speed
        if self.kind == OBS_BIRD:
            self.y = self._base_y + math.sin(tick * 0.05 + self._phase) * 18

    def draw(self, surface: pygame.Surface, tick: int) -> None:
        r = self.rect()
        if self.kind == OBS_BLOCK:
            pygame.draw.rect(surface, OBSTACLE_COL, r, border_radius=4)
            pygame.draw.rect(surface, (100, 78, 54),
                             (r.x + 4, r.y + 4, r.w - 8, 4), border_radius=2)
        elif self.kind == OBS_SPIKE:
            pts = [(r.x, r.y + r.h), (r.x + r.w // 2, r.y), (r.x + r.w, r.y + r.h)]
            pygame.draw.polygon(surface, SPIKE_COL, pts)
            pygame.draw.polygon(surface, (130, 130, 135), pts, 2)
        elif self.kind == OBS_BUSH:
            pygame.draw.ellipse(surface, BUSH_COL, r)
            pygame.draw.ellipse(surface, (60, 130, 50), r, 2)
            for lx in range(r.x + 6, r.x + r.w - 6, 8):
                pygame.draw.circle(surface, (95, 165, 75), (lx, r.y + r.h // 3), 3)
        elif self.kind == OBS_BIRD:
            cx, cy = r.x + r.w // 2, r.y + r.h // 2
            wing = math.sin(tick * 0.2 + self._phase) * 6
            pygame.draw.ellipse(surface, BIRD_COL, (cx - 10, cy - 5, 20, 10))
            pygame.draw.polygon(surface, BIRD_COL, [
                (cx - 8, cy), (cx - 18, cy - 8 + wing), (cx - 4, cy - 2)])
            pygame.draw.polygon(surface, BIRD_COL, [
                (cx + 8, cy), (cx + 18, cy - 8 - wing), (cx + 4, cy - 2)])
            pygame.draw.circle(surface, (220, 180, 40), (cx + 8, cy - 2), 2)
            pygame.draw.polygon(surface, (200, 140, 40),
                                [(cx + 11, cy), (cx + 16, cy + 1), (cx + 11, cy + 2)])

    def off_screen(self) -> bool:
        return self.x + self.w < 0

# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------

@dataclass
class Platform:
    x: float
    y: float
    w: int = 80
    speed: float = 2.5

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, 12)

    def update(self) -> None:
        self.x -= self.speed

    def off_screen(self) -> bool:
        return self.x + self.w < 0

    def draw(self, surface: pygame.Surface) -> None:
        r = self.rect()
        pygame.draw.rect(surface, PLATFORM_COL, r, border_radius=3)
        pygame.draw.rect(surface, PLATFORM_TOP, (r.x, r.y, r.w, 4), border_radius=2)

# ---------------------------------------------------------------------------
# Mouse (collectible)
# ---------------------------------------------------------------------------

@dataclass
class Mouse:
    x: float
    y: float
    radius: int = 14
    speed: float = 2.8
    collected: bool = False
    _phase: float = field(default_factory=lambda: random.uniform(0, math.tau))

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius),
                           self.radius * 2, self.radius * 2)

    def update(self) -> None:
        self.x -= self.speed

    def off_screen(self) -> bool:
        return self.x + self.radius < 0

    def draw(self, surface: pygame.Surface, tick: int) -> None:
        if self.collected:
            return
        bob = math.sin(tick * 0.08 + self._phase) * 3
        cx, cy = int(self.x), int(self.y + bob)
        pygame.draw.ellipse(surface, MOUSE_BODY, (cx - 12, cy - 7, 24, 14))
        pygame.draw.circle(surface, MOUSE_EAR, (cx - 7, cy - 9), 5)
        pygame.draw.circle(surface, MOUSE_EAR, (cx + 7, cy - 9), 5)
        pygame.draw.circle(surface, MOUSE_BODY, (cx - 7, cy - 9), 3)
        pygame.draw.circle(surface, MOUSE_BODY, (cx + 7, cy - 9), 3)
        pygame.draw.circle(surface, BLACK, (cx + 8, cy - 2), 2)
        pygame.draw.circle(surface, MOUSE_DARK, (cx + 13, cy), 2)
        tail_pts = [(cx - 12, cy), (cx - 20, cy - 8), (cx - 26, cy - 4)]
        pygame.draw.lines(surface, MOUSE_DARK, False, tail_pts, 2)

# ---------------------------------------------------------------------------
# Power-up
# ---------------------------------------------------------------------------

POWERUP_SHIELD = "shield"
POWERUP_MAGNET = "magnet"
POWERUP_SPEED = "speed"

@dataclass
class PowerUp:
    x: float
    y: float
    kind: str
    speed: float = 2.8
    collected: bool = False
    _phase: float = field(default_factory=lambda: random.uniform(0, math.tau))

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) - 13, int(self.y) - 13, 26, 26)

    def update(self) -> None:
        self.x -= self.speed

    def off_screen(self) -> bool:
        return self.x + 13 < 0

    def draw(self, surface: pygame.Surface, tick: int) -> None:
        if self.collected:
            return
        bob = math.sin(tick * 0.07 + self._phase) * 4
        cx, cy = int(self.x), int(self.y + bob)

        if self.kind == POWERUP_SHIELD:
            pygame.draw.circle(surface, SHIELD_COL, (cx, cy), 13)
            pygame.draw.circle(surface, (60, 140, 220), (cx, cy), 13, 2)
            pygame.draw.circle(surface, WHITE, (cx, cy), 6, 2)
        elif self.kind == POWERUP_MAGNET:
            pygame.draw.circle(surface, MAGNET_COL, (cx, cy), 13)
            pygame.draw.circle(surface, (200, 50, 50), (cx, cy), 13, 2)
            pygame.draw.arc(surface, WHITE, (cx - 6, cy - 8, 12, 12), 0, math.pi, 3)
            pygame.draw.line(surface, WHITE, (cx - 6, cy - 2), (cx - 6, cy + 6), 3)
            pygame.draw.line(surface, WHITE, (cx + 6, cy - 2), (cx + 6, cy + 6), 3)
        elif self.kind == POWERUP_SPEED:
            pygame.draw.circle(surface, SPEED_COL, (cx, cy), 13)
            pygame.draw.circle(surface, (200, 170, 30), (cx, cy), 13, 2)
            bolt = [(cx - 2, cy - 9), (cx + 4, cy - 1), (cx, cy - 1),
                    (cx + 3, cy + 9), (cx - 4, cy + 1), (cx, cy + 1)]
            pygame.draw.polygon(surface, WHITE, bolt)

# ---------------------------------------------------------------------------
# Sparkle particle
# ---------------------------------------------------------------------------

@dataclass
class Sparkle:
    x: float
    y: float
    vx: float
    vy: float
    life: float = 0.45
    color: tuple = (255, 255, 200)

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.life <= 0:
            return
        frac = self.life / 0.45
        r = max(1, int(3 * frac))
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), r)


def spawn_sparkles(x: float, y: float,
                   color: tuple = (255, 255, 200)) -> list[Sparkle]:
    out: list[Sparkle] = []
    for _ in range(6):
        angle = random.uniform(0, math.tau)
        spd = random.uniform(40, 120)
        out.append(Sparkle(x=x, y=y, vx=math.cos(angle) * spd,
                           vy=math.sin(angle) * spd, color=color))
    return out

# ---------------------------------------------------------------------------
# Level helpers & spawning
# ---------------------------------------------------------------------------

def level_speed(level: int) -> tuple[float, float]:
    lo = 2.4 + (level - 1) * 0.25
    hi = 3.2 + (level - 1) * 0.3
    return lo, hi


def level_spacing(level: int) -> tuple[int, int]:
    lo = max(180, 260 - (level - 1) * 18)
    hi = max(280, 430 - (level - 1) * 22)
    return lo, hi


def _rand_speed(level: int) -> float:
    lo, hi = level_speed(level)
    return random.uniform(lo, hi)


def make_obstacle(last_x: float, level: int) -> Obstacle:
    sp_lo, sp_hi = level_spacing(level)
    spacing = random.randint(sp_lo, sp_hi)
    x = max(WIDTH + 20, last_x + spacing)
    speed = _rand_speed(level)

    kind_roll = random.random()
    if level >= 2 and kind_roll < 0.18:
        kind = OBS_BIRD
        w, h = 30, 18
        y = GROUND_Y - random.choice([50, 75, 100, 130])
        return Obstacle(x=x, y=y, w=w, h=h, speed=speed, kind=kind)
    elif level >= 1 and kind_roll < 0.40:
        kind = OBS_SPIKE
        w = random.randint(24, 36)
        h = random.randint(30, 55)
    elif kind_roll < 0.60:
        kind = OBS_BUSH
        w = random.randint(40, 65)
        h = random.randint(25, 40)
    else:
        kind = OBS_BLOCK
        w = random.randint(26, 46)
        h = random.randint(35, 70)

    y = GROUND_Y - h
    return Obstacle(x=x, y=y, w=w, h=h, speed=speed, kind=kind)


def make_mouse(obstacle: Obstacle, level: int) -> Mouse | None:
    if random.random() > 0.55:
        return None
    my = obstacle.y - random.randint(24, 60)
    my = max(60, my)
    return Mouse(x=obstacle.x + obstacle.w / 2, y=my,
                 speed=_rand_speed(level))


def make_powerup(obstacle: Obstacle, level: int) -> PowerUp | None:
    if random.random() > 0.12:
        return None
    kind = random.choice([POWERUP_SHIELD, POWERUP_MAGNET, POWERUP_SPEED])
    py = obstacle.y - random.randint(40, 80)
    py = max(50, py)
    return PowerUp(x=obstacle.x + obstacle.w / 2, y=py, kind=kind,
                   speed=_rand_speed(level))


def make_platform(last_x: float, level: int) -> Platform | None:
    if random.random() > 0.30:
        return None
    w = random.randint(60, 110)
    x = max(WIDTH + 40, last_x + random.randint(200, 380))
    y = GROUND_Y - random.randint(60, 130)
    return Platform(x=x, y=y, w=w, speed=_rand_speed(level))

# ---------------------------------------------------------------------------
# Parallax background
# ---------------------------------------------------------------------------

def draw_parallax(screen: pygame.Surface, offsets: list[float],
                  level: int) -> None:
    sky_r = max(130, SKY[0] - (level - 1) * 6)
    sky_g = max(180, SKY[1] - (level - 1) * 4)
    sky_b = min(255, SKY[2] + (level - 1) * 2)
    screen.fill((sky_r, sky_g, sky_b))

    # Clouds
    for i in range(4):
        cx = (i * 260 + offsets[0]) % (WIDTH + 200) - 100
        cy = 55 + (i % 2) * 25
        pygame.draw.ellipse(screen, WHITE, (cx, cy, 70, 36))
        pygame.draw.ellipse(screen, WHITE, (cx + 20, cy - 10, 70, 40))
        pygame.draw.ellipse(screen, WHITE, (cx + 42, cy, 70, 36))

    # Far hills
    for i in range(4):
        hx = (i * 300 + offsets[1]) % (WIDTH + 350) - 175
        pygame.draw.ellipse(screen, FAR_HILL, (hx, GROUND_Y - 55, 280, 110))

    # Mid trees
    for i in range(6):
        tx = (i * 170 + offsets[2]) % (WIDTH + 160) - 80
        pygame.draw.rect(screen, TRUNK_COL, (tx + 7, GROUND_Y - 36, 7, 36))
        pygame.draw.circle(screen, MID_TREE, (tx + 10, GROUND_Y - 42), 16)
        pygame.draw.circle(screen, (80, 150, 60), (tx + 10, GROUND_Y - 42), 16, 2)

    # Near bushes
    for i in range(8):
        bx = (i * 130 + offsets[3]) % (WIDTH + 120) - 60
        pygame.draw.ellipse(screen, BUSH_COL, (bx, GROUND_Y - 10, 36, 22))

    # Ground
    pygame.draw.rect(screen, GROUND_COL, (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
    for gx in range(0, WIDTH, 28):
        pygame.draw.rect(screen, DARK_GROUND, (gx, GROUND_Y, 14, 6), border_radius=3)


def update_parallax(offsets: list[float], dt: float) -> None:
    base = 60 * dt
    offsets[0] -= base * 0.15   # clouds
    offsets[1] -= base * 0.3    # far hills
    offsets[2] -= base * 0.6    # trees
    offsets[3] -= base * 1.0    # bushes

# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    cat: Cat
    obstacles: list[Obstacle]
    mice: list[Mouse]
    platforms: list[Platform]
    powerups: list[PowerUp]
    score: int = 0
    mice_caught: int = 0
    level: int = 1
    obstacles_cleared: int = 0
    game_over: bool = False
    level_transition_timer: float = 0.0
    parallax: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])


def new_game(skin: str = "orange") -> GameState:
    cat = Cat(skin=skin)
    obs1 = make_obstacle(WIDTH + 10, 1)
    obs2 = make_obstacle(obs1.x, 1)
    mice: list[Mouse] = []
    powerups: list[PowerUp] = []
    platforms: list[Platform] = []
    for o in (obs1, obs2):
        m = make_mouse(o, 1)
        if m:
            mice.append(m)
        p = make_powerup(o, 1)
        if p:
            powerups.append(p)
    pl = make_platform(WIDTH + 60, 1)
    if pl:
        platforms.append(pl)
    return GameState(cat=cat, obstacles=[obs1, obs2], mice=mice,
                     platforms=platforms, powerups=powerups)

# ---------------------------------------------------------------------------
# HUD & UI drawing
# ---------------------------------------------------------------------------

def draw_hearts(screen: pygame.Surface, lives: int, x: int, y: int) -> None:
    for i in range(3):
        cx = x + i * 26
        col = HEART_COL if i < lives else (80, 80, 80)
        pygame.draw.polygon(screen, col, [
            (cx, y + 4), (cx - 6, y - 2), (cx - 6, y - 6),
            (cx - 3, y - 9), (cx, y - 6),
            (cx + 3, y - 9), (cx + 6, y - 6), (cx + 6, y - 2),
        ])


def draw_powerup_indicators(screen: pygame.Surface, cat: Cat,
                             x: int, y: int) -> None:
    indicators: list[tuple[str, tuple, float]] = []
    if cat.shield:
        indicators.append(("S", SHIELD_COL, 1.0))
    if cat.magnet_timer > 0:
        indicators.append(("M", MAGNET_COL, min(1.0, cat.magnet_timer / 8)))
    if cat.speed_boost_timer > 0:
        indicators.append(("F", SPEED_COL, min(1.0, cat.speed_boost_timer / 6)))
    for i, (label, col, frac) in enumerate(indicators):
        ix = x + i * 30
        pygame.draw.rect(screen, col, (ix, y, 22, 14), border_radius=3)
        bar_w = int(20 * frac)
        pygame.draw.rect(screen, (*col, 180), (ix + 1, y + 11, bar_w, 3), border_radius=1)


def draw_start_menu(screen: pygame.Surface, font: pygame.font.Font,
                    small: pygame.font.Font, tick: int,
                    best: int, save_data: dict) -> None:
    draw_parallax(screen, [tick * -0.15, tick * -0.3, tick * -0.5, tick * -0.8], 1)
    bob = math.sin(tick * 0.04) * 6
    cat = Cat(x=WIDTH // 2 - 28, y=GROUND_Y - 56 + bob,
              skin=save_data["selected_skin"])
    cat.draw(screen, tick)

    title = font.render("Cat Platformer", True, TITLE_COL)
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))

    if best > 0:
        bs = small.render(f"Best Score: {best}", True, TITLE_COL)
        screen.blit(bs, (WIDTH // 2 - bs.get_width() // 2, 90))

    alpha = int(180 + 75 * math.sin(tick * 0.06))
    prompt = small.render("SPACE  start  |  S  skins", True, BLACK)
    prompt.set_alpha(alpha)
    screen.blit(prompt, (WIDTH // 2 - prompt.get_width() // 2, HEIGHT // 2 + 50))

    controls = small.render("A/D move  |  Space jump  |  ESC pause", True, (80, 80, 80))
    screen.blit(controls, (WIDTH // 2 - controls.get_width() // 2, HEIGHT // 2 + 78))

    mice_t = small.render(f"Mice: {save_data['total_mice']}", True, MOUSE_DARK)
    screen.blit(mice_t, (WIDTH // 2 - mice_t.get_width() // 2, HEIGHT // 2 + 106))


def draw_skin_shop(screen: pygame.Surface, font: pygame.font.Font,
                   small: pygame.font.Font, tick: int,
                   save_data: dict, cursor: int) -> None:
    screen.fill((240, 235, 225))
    title = font.render("Skin Shop", True, TITLE_COL)
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 20))

    mice_t = small.render(f"Your mice: {save_data['total_mice']}", True, MOUSE_DARK)
    screen.blit(mice_t, (WIDTH // 2 - mice_t.get_width() // 2, 58))

    card_w, card_h = 130, 200
    total_w = len(SKIN_ORDER) * card_w + (len(SKIN_ORDER) - 1) * 16
    start_x = WIDTH // 2 - total_w // 2

    for i, sid in enumerate(SKIN_ORDER):
        sk = SKINS[sid]
        cx = start_x + i * (card_w + 16)
        cy = 100

        bg = (255, 250, 240) if i != cursor else (255, 240, 200)
        pygame.draw.rect(screen, bg, (cx, cy, card_w, card_h), border_radius=8)
        if i == cursor:
            pygame.draw.rect(screen, GOLD, (cx, cy, card_w, card_h), 3, border_radius=8)

        preview_cat = Cat(x=cx + card_w // 2 - 28, y=cy + 30, skin=sid)
        preview_cat.draw(screen, tick)

        name = small.render(sk["name"], True, BLACK)
        screen.blit(name, (cx + card_w // 2 - name.get_width() // 2, cy + 110))

        owned = sid in save_data["unlocked_skins"]
        selected = save_data["selected_skin"] == sid
        if selected:
            tag = small.render("SELECTED", True, (30, 140, 30))
        elif owned:
            tag = small.render("OWNED", True, (80, 80, 80))
        else:
            tag = small.render(f"Cost: {sk['cost']}", True, GOLD_DARK)
        screen.blit(tag, (cx + card_w // 2 - tag.get_width() // 2, cy + 135))

        if i == cursor:
            if not owned:
                hint = small.render("ENTER to buy", True, BLACK)
            elif not selected:
                hint = small.render("ENTER to select", True, BLACK)
            else:
                hint = small.render("In use!", True, (30, 140, 30))
            screen.blit(hint, (cx + card_w // 2 - hint.get_width() // 2, cy + 165))

    esc = small.render("ESC  back to menu", True, (120, 120, 120))
    screen.blit(esc, (WIDTH // 2 - esc.get_width() // 2, HEIGHT - 40))


def draw_pause(screen: pygame.Surface, font: pygame.font.Font,
               small: pygame.font.Font) -> None:
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))
    screen.blit(overlay, (0, 0))
    t = font.render("PAUSED", True, WHITE)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, HEIGHT // 2 - 30))
    s = small.render("Press ESC to resume", True, (200, 200, 200))
    screen.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT // 2 + 10))


def draw_level_banner(screen: pygame.Surface, font: pygame.font.Font,
                      level: int, timer: float) -> None:
    progress = max(0.0, min(1.0, timer / 1.4))
    alpha = int(100 * progress)
    banner = pygame.Surface((WIDTH, 60), pygame.SRCALPHA)
    banner.fill((0, 0, 0, alpha))
    screen.blit(banner, (0, HEIGHT // 2 - 30))
    text = font.render(f"Level {level}  —  Get ready!", True, GOLD)
    text.set_alpha(int(255 * progress))
    screen.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - 22))

# ---------------------------------------------------------------------------
# Sound effects
# ---------------------------------------------------------------------------

WEB_SR = 11025


def _make_sound(samples: list[int]) -> pygame.mixer.Sound:
    buf = array.array("h", samples)
    return pygame.mixer.Sound(buffer=buf)


def _web_tone(freq: float, dur: float, vol: float = 0.22) -> list[int]:
    n = int(WEB_SR * dur)
    return [int(math.sin(2 * math.pi * freq * i / WEB_SR) * vol * (1 - i / n) * 32767)
            for i in range(n)]


def create_web_sound_queue() -> list[tuple[str, object]]:
    """Return (name, callable) pairs that each generate one short sound."""
    t = _web_tone
    def mk(*parts: list[int]) -> pygame.mixer.Sound:
        samples: list[int] = []
        for p in parts:
            samples += p
        return _make_sound(samples)

    return [
        ("jump",         lambda: mk(t(420, 0.05), t(560, 0.05))),
        ("double_jump",  lambda: mk(t(560, 0.04), t(750, 0.04), t(900, 0.03))),
        ("catch",        lambda: mk(t(880, 0.06), t(1100, 0.08))),
        ("hit",          lambda: mk(t(120, 0.10, 0.3))),
        ("life_lost",    lambda: mk(t(400, 0.07), t(300, 0.07), t(200, 0.09))),
        ("shield_break", lambda: mk(t(300, 0.08))),
        ("powerup",      lambda: mk(t(660, 0.05), t(880, 0.05), t(1100, 0.06))),
        ("level_up",     lambda: mk(t(523, 0.07), t(659, 0.07), t(784, 0.07), t(1047, 0.07))),
        ("pause",        lambda: mk(t(500, 0.06))),
        ("buy",          lambda: mk(t(523, 0.06), t(659, 0.06), t(784, 0.06), t(1047, 0.07))),
        ("start",        lambda: mk(t(523, 0.10), t(659, 0.08), t(784, 0.08))),
    ]


def _tone(freq: float, duration: float, volume: float = 0.25,
          fade_out: bool = True) -> list[int]:
    n = int(SAMPLE_RATE * duration)
    out: list[int] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = 1.0 - (i / n) if fade_out else 1.0
        out.append(int(math.sin(2 * math.pi * freq * t) * volume * env * 32767))
    return out


def _noise_burst(duration: float, volume: float = 0.15) -> list[int]:
    n = int(SAMPLE_RATE * duration)
    return [int(random.uniform(-1, 1) * volume * (1.0 - i / n) * 32767)
            for i in range(n)]


def _melody_note(freq: float, duration: float, volume: float = 0.08) -> list[int]:
    n = int(SAMPLE_RATE * duration)
    attack = int(n * 0.08)
    release = int(n * 0.25)
    out: list[int] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        if i < attack:
            env = i / attack
        elif i > n - release:
            env = (n - i) / release
        else:
            env = 1.0
        wave = (math.sin(2 * math.pi * freq * t) * 0.7 +
                math.sin(2 * math.pi * freq * 2 * t) * 0.2 +
                math.sin(2 * math.pi * freq * 3 * t) * 0.1)
        out.append(int(wave * volume * env * 32767))
    return out


def create_sounds() -> dict[str, pygame.mixer.Sound]:
    sfx: dict[str, pygame.mixer.Sound] = {}
    sfx["jump"] = _make_sound(_tone(420, 0.07, 0.2) + _tone(560, 0.07, 0.18))
    sfx["double_jump"] = _make_sound(
        _tone(560, 0.05, 0.18) + _tone(750, 0.06, 0.16) + _tone(900, 0.05, 0.12))
    sfx["catch"] = _make_sound(_tone(880, 0.08, 0.2) + _tone(1100, 0.12, 0.22))
    sfx["hit"] = _make_sound(_tone(120, 0.12, 0.3) + _noise_burst(0.15, 0.12))
    sfx["life_lost"] = _make_sound(
        _tone(400, 0.1, 0.2) + _tone(300, 0.1, 0.2) + _tone(200, 0.15, 0.2))
    sfx["shield_break"] = _make_sound(_noise_burst(0.2, 0.2) + _tone(300, 0.1, 0.15))
    sfx["powerup"] = _make_sound(
        _tone(660, 0.06, 0.15) + _tone(880, 0.06, 0.15) + _tone(1100, 0.08, 0.18))
    sfx["level_up"] = _make_sound(
        sum([_tone(n, 0.1, 0.2) for n in [523, 659, 784, 1047]], []))
    sfx["pause"] = _make_sound(_tone(500, 0.08, 0.12))
    sfx["buy"] = _make_sound(
        _tone(523, 0.08, 0.15) + _tone(659, 0.08, 0.15) +
        _tone(784, 0.08, 0.15) + _tone(1047, 0.12, 0.18))

    dur = 0.18
    n = int(SAMPLE_RATE * dur)
    start_samples: list[int] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = 1.0 - (i / n)
        val = (math.sin(2 * math.pi * 523 * t) * 0.15 +
               math.sin(2 * math.pi * 659 * t) * 0.12 +
               math.sin(2 * math.pi * 784 * t) * 0.10) * env
        start_samples.append(int(val * 32767))
    sfx["start"] = _make_sound(start_samples)

    return sfx


def _build_bgm(notes: list[tuple[float, float]], vol: float) -> pygame.mixer.Sound:
    samples: list[int] = []
    for freq, dur in notes:
        if freq == 0:
            samples += [0] * int(SAMPLE_RATE * dur)
        else:
            samples += _melody_note(freq, dur, volume=vol)
    return _make_sound(samples)


def create_bgm_menu() -> pygame.mixer.Sound:
    return _build_bgm([
        (523, 0.45), (587, 0.45), (659, 0.45), (784, 0.9),
        (659, 0.45), (587, 0.45), (523, 0.9),
        (392, 0.45), (440, 0.45), (523, 0.45), (587, 0.9),
        (523, 0.45), (440, 0.45), (392, 0.9),
        (523, 0.45), (659, 0.45), (784, 0.45), (880, 0.9),
        (784, 0.45), (659, 0.45), (523, 0.9),
        (440, 0.45), (523, 0.45), (587, 0.45), (523, 0.9),
        (0, 0.45),
    ], 0.06)


def create_bgm_game() -> pygame.mixer.Sound:
    return _build_bgm([
        (523, 0.3), (587, 0.3), (659, 0.3), (784, 0.3),
        (880, 0.6), (784, 0.3), (659, 0.6),
        (587, 0.3), (523, 0.3), (440, 0.3), (523, 0.3),
        (587, 0.6), (0, 0.3),
        (659, 0.3), (784, 0.3), (880, 0.3), (784, 0.3),
        (659, 0.3), (587, 0.3), (523, 0.6),
        (440, 0.3), (392, 0.3), (440, 0.3), (523, 0.3),
        (587, 0.6), (523, 0.6), (0, 0.3),
    ], 0.05)

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def main() -> None:
    if IS_WEB:
        pygame.init()
        try:
            pygame.mixer.init(WEB_SR, -16, 1, 512)
            _web_sound_queue = create_web_sound_queue()
        except Exception:
            _web_sound_queue = []
    else:
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
        pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Cat Platformer")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 28, bold=True)
    small = pygame.font.SysFont("consolas", 18)
    hud_font = pygame.font.SysFont("consolas", 22)

    if IS_WEB:
        sfx: dict = _SilentDict()
        bgm_menu: object = _NoSound()
        bgm_game: object = _NoSound()
    else:
        pygame.mixer.set_num_channels(16)
        sfx = create_sounds()
        bgm_menu = create_bgm_menu()
        bgm_game = create_bgm_game()

    bgm_channel = _NoSound() if IS_WEB else pygame.mixer.Channel(0)

    def play_bgm(track: object) -> None:
        try:
            bgm_channel.stop()
            bgm_channel.play(track, loops=-1)
        except Exception:
            pass

    save_data = load_save()

    state: GameState | None = None
    in_menu = True
    in_shop = False
    paused = False
    shop_cursor = 0
    running = True
    tick = 0
    sparkles: list[Sparkle] = []

    play_bgm(bgm_menu)

    while running:
        dt = clock.tick(FPS) / 1000.0
        tick += 1
        jump_pressed = False

        if IS_WEB and _web_sound_queue:
            try:
                _sname, _sgen = _web_sound_queue.pop(0)
                sfx[_sname] = _sgen()
            except Exception:
                pass

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                # --- Skin shop ---
                if in_shop:
                    if event.key == pygame.K_ESCAPE:
                        in_shop = False
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        shop_cursor = (shop_cursor - 1) % len(SKIN_ORDER)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        shop_cursor = (shop_cursor + 1) % len(SKIN_ORDER)
                    elif event.key == pygame.K_RETURN:
                        sid = SKIN_ORDER[shop_cursor]
                        sk = SKINS[sid]
                        if sid not in save_data["unlocked_skins"]:
                            if save_data["total_mice"] >= sk["cost"]:
                                save_data["total_mice"] -= sk["cost"]
                                save_data["unlocked_skins"].append(sid)
                                save_data["selected_skin"] = sid
                                write_save(save_data)
                                sfx["buy"].play()
                        elif save_data["selected_skin"] != sid:
                            save_data["selected_skin"] = sid
                            write_save(save_data)
                            sfx["start"].play()
                    continue

                # --- Menu ---
                if in_menu:
                    if event.key == pygame.K_SPACE:
                        state = new_game(save_data["selected_skin"])
                        sparkles.clear()
                        paused = False
                        in_menu = False
                        sfx["start"].play()
                        play_bgm(bgm_game)
                    elif event.key == pygame.K_s:
                        in_shop = True
                    continue

                # --- Pause toggle ---
                if event.key == pygame.K_ESCAPE and state and not state.game_over:
                    paused = not paused
                    sfx["pause"].play()
                    continue

                # --- Game over ---
                if state and state.game_over:
                    if event.key == pygame.K_r:
                        save_data["best_score"] = max(
                            save_data["best_score"], state.score)
                        write_save(save_data)
                        state = new_game(save_data["selected_skin"])
                        sparkles.clear()
                        sfx["start"].play()
                        play_bgm(bgm_game)
                    elif event.key == pygame.K_m:
                        save_data["best_score"] = max(
                            save_data["best_score"], state.score)
                        write_save(save_data)
                        state = None
                        in_menu = True
                        play_bgm(bgm_menu)
                    continue

                # --- Jump ---
                if event.key in (pygame.K_SPACE, pygame.K_w, pygame.K_UP):
                    jump_pressed = True

        # ---- Render-only states ----
        if in_shop:
            draw_skin_shop(screen, font, small, tick, save_data, shop_cursor)
            await asyncio.sleep(0)
            pygame.display.flip()
            continue

        if in_menu:
            draw_start_menu(screen, font, small, tick,
                            save_data["best_score"], save_data)
            await asyncio.sleep(0)
            pygame.display.flip()
            continue

        assert state is not None

        if paused:
            # Still draw the game underneath
            draw_parallax(screen, state.parallax, state.level)
            for pl in state.platforms:
                pl.draw(screen)
            for obs in state.obstacles:
                obs.draw(screen, tick)
            for mouse in state.mice:
                mouse.draw(screen, tick)
            for pu in state.powerups:
                pu.draw(screen, tick)
            state.cat.draw(screen, tick)
            draw_pause(screen, font, small)
            await asyncio.sleep(0)
            pygame.display.flip()
            continue

        keys = pygame.key.get_pressed()
        move_left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        move_right = keys[pygame.K_d] or keys[pygame.K_RIGHT]

        if state.level_transition_timer > 0:
            state.level_transition_timer -= dt

        # ---- Game update ----
        if not state.game_over:
            jumps_before = state.cat.jumps_left
            state.cat.update(move_left, move_right, jump_pressed,
                             state.platforms, dt)
            if state.cat.jumps_left < jumps_before:
                if jumps_before == state.cat.max_jumps:
                    sfx["jump"].play()
                else:
                    sfx["double_jump"].play()
                    state.cat.spin_timer = 0.4

            update_parallax(state.parallax, dt)

            for obs in state.obstacles:
                obs.update(tick)
            for mouse in state.mice:
                mouse.update()
            for pu in state.powerups:
                pu.update()
            for pl in state.platforms:
                pl.update()

            # Magnet effect
            if state.cat.magnet_timer > 0:
                cat_cx = state.cat.x + state.cat.w / 2
                cat_cy = state.cat.y + state.cat.h / 2
                for mouse in state.mice:
                    if mouse.collected:
                        continue
                    dx = cat_cx - mouse.x
                    dy = cat_cy - mouse.y
                    dist = math.hypot(dx, dy)
                    if 0 < dist < 160:
                        mouse.x += dx / dist * 3.5
                        mouse.y += dy / dist * 3.5

            # Score on passing obstacles
            cat_cx = state.cat.x + state.cat.w / 2
            for obs in state.obstacles:
                if not obs.scored and obs.x + obs.w < cat_cx:
                    obs.scored = True
                    state.obstacles_cleared += 1
                    state.score += 1

            # Spawn new obstacles/mice/powerups/platforms
            if state.obstacles and state.obstacles[0].off_screen():
                state.obstacles.pop(0)
                new_obs = make_obstacle(state.obstacles[-1].x, state.level)
                state.obstacles.append(new_obs)
                m = make_mouse(new_obs, state.level)
                if m:
                    state.mice.append(m)
                p = make_powerup(new_obs, state.level)
                if p:
                    state.powerups.append(p)

            last_plat_x = max((pl.x for pl in state.platforms), default=0)
            pl = make_platform(last_plat_x, state.level)
            if pl and len(state.platforms) < 4:
                state.platforms.append(pl)

            state.mice = [m for m in state.mice if not m.off_screen()]
            state.powerups = [p for p in state.powerups if not p.off_screen()]
            state.platforms = [p for p in state.platforms if not p.off_screen()]

            # Mouse collection
            cat_hitbox = state.cat.rect().inflate(-8, -6)
            for mouse in state.mice:
                if not mouse.collected and cat_hitbox.colliderect(mouse.rect()):
                    mouse.collected = True
                    state.mice_caught += 1
                    save_data["total_mice"] += 1
                    state.score += 3
                    sparkles.extend(spawn_sparkles(mouse.x, mouse.y))
                    sfx["catch"].play()
            state.mice = [m for m in state.mice if not m.collected]

            # Power-up collection
            for pu in state.powerups:
                if not pu.collected and cat_hitbox.colliderect(pu.rect()):
                    pu.collected = True
                    sfx["powerup"].play()
                    sparkles.extend(
                        spawn_sparkles(pu.x, pu.y, color=SHIELD_COL if pu.kind == POWERUP_SHIELD
                                       else MAGNET_COL if pu.kind == POWERUP_MAGNET
                                       else SPEED_COL))
                    if pu.kind == POWERUP_SHIELD:
                        state.cat.shield = True
                    elif pu.kind == POWERUP_MAGNET:
                        state.cat.magnet_timer = 8.0
                    elif pu.kind == POWERUP_SPEED:
                        state.cat.speed_boost_timer = 6.0
            state.powerups = [p for p in state.powerups if not p.collected]

            # Obstacle collision
            if state.cat.invincible_timer <= 0:
                for obs in state.obstacles:
                    if cat_hitbox.colliderect(obs.rect()):
                        if state.cat.shield:
                            state.cat.shield = False
                            state.cat.invincible_timer = 1.0
                            sfx["shield_break"].play()
                            sparkles.extend(
                                spawn_sparkles(state.cat.x + state.cat.w / 2,
                                               state.cat.y + state.cat.h / 2,
                                               color=SHIELD_COL))
                        else:
                            state.cat.lives -= 1
                            sfx["life_lost"].play()
                            if state.cat.lives <= 0:
                                state.game_over = True
                                sfx["hit"].play()
                                save_data["best_score"] = max(
                                    save_data["best_score"], state.score)
                                write_save(save_data)
                            else:
                                state.cat.invincible_timer = 2.0
                        break

            # Level-up
            if state.obstacles_cleared >= OBSTACLES_PER_LEVEL * state.level:
                state.level += 1
                state.level_transition_timer = 1.4
                sfx["level_up"].play()

        # Sparkles
        for s in sparkles:
            s.update(dt)
        sparkles = [s for s in sparkles if s.life > 0]

        # ---- Drawing ----
        draw_parallax(screen, state.parallax, state.level)

        for pl in state.platforms:
            pl.draw(screen)
        for obs in state.obstacles:
            obs.draw(screen, tick)
        for mouse in state.mice:
            mouse.draw(screen, tick)
        for pu in state.powerups:
            pu.draw(screen, tick)
        for s in sparkles:
            s.draw(screen)

        state.cat.draw(screen, tick)

        # HUD
        score_s = font.render(f"Score: {state.score}", True, BLACK)
        screen.blit(score_s, (18, 10))
        mice_s = hud_font.render(f"Mice: {state.mice_caught}", True, MOUSE_DARK)
        screen.blit(mice_s, (18, 42))

        draw_hearts(screen, state.cat.lives, WIDTH - 90, 22)
        level_s = small.render(f"Level {state.level}", True, BLACK)
        screen.blit(level_s, (WIDTH - level_s.get_width() - 18, 38))
        draw_powerup_indicators(screen, state.cat, WIDTH - 108, 56)

        if state.level_transition_timer > 0:
            draw_level_banner(screen, font, state.level,
                              state.level_transition_timer)

        if state.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 130))
            screen.blit(overlay, (0, 0))
            lines = [
                font.render("Oh no! The cat ran out of lives.", True, WHITE),
                small.render(
                    f"Score: {state.score}   Mice: {state.mice_caught}"
                    f"   Level: {state.level}", True, GOLD),
                small.render(f"Best: {save_data['best_score']}", True, SPARKLE_COL),
                small.render("R  retry  |  M  menu", True, WHITE),
            ]
            y_start = HEIGHT // 2 - 50
            for i, line in enumerate(lines):
                screen.blit(line, (WIDTH // 2 - line.get_width() // 2,
                                   y_start + i * 32))

        await asyncio.sleep(0)
        pygame.display.flip()

    pygame.quit()


asyncio.run(main())
