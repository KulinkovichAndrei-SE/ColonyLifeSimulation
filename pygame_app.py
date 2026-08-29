"""Pygame presentation and interaction layer for the deterministic engine.

The UI owns input, camera/layout, and drawing only.  All world changes go
through :class:`colony_simulation.ColonySimulation` methods or one explicit
``step`` call, so the same state can still be tested and replayed headlessly.
"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence, Tuple

from colony_simulation import ColonyConfig, ColonySimulation


COLONY_COLORS = ((80, 170, 255), (255, 120, 120), (130, 230, 120), (220, 170, 255))
BACKGROUND = (18, 24, 30)
PANEL = (30, 39, 48)
GRID = (48, 63, 72)
TEXT = (235, 240, 242)
MUTED = (160, 175, 180)
RESOURCE_COLORS = {"wood": (100, 190, 90), "grain": (235, 205, 80)}


class PygameSimulationApp:
    """Interactive Pygame view over one deterministic colony simulation."""

    def __init__(
        self,
        simulation: Optional[ColonySimulation] = None,
        *,
        window_size: Tuple[int, int] = (1440, 900),
        frames_per_second: int = 12,
    ) -> None:
        import pygame

        if frames_per_second <= 0:
            raise ValueError("frames_per_second must be positive")
        self.pygame = pygame
        pygame.init()
        self.screen = pygame.display.set_mode(window_size)
        pygame.display.set_caption("Colony Life Simulation")
        self.ui_clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16)
        self.small_font = pygame.font.SysFont("consolas", 13)
        self.title_font = pygame.font.SysFont("consolas", 20, bold=True)
        self.simulation = simulation or ColonySimulation(
            ColonyConfig(seed=20260828, width=40, height=28, population=12, settlement_count=2, ai_enabled=True)
        )
        self.frames_per_second = frames_per_second
        self.running = True
        self.paused = False
        self.selected_agent_id: Optional[str] = None
        self.selected_settlement_id = "settlement-000"
        self.status_message = "Running. Click a resident to inspect it."
        map_width = int(window_size[0] * 0.63)
        self._map_rect = pygame.Rect(18, 18, map_width, window_size[1] - 150)
        self._panel_rect = pygame.Rect(map_width + 36, 18, window_size[0] - map_width - 54, window_size[1] - 36)

    def close(self) -> None:
        self.pygame.quit()

    def run(self, max_frames: Optional[int] = None) -> int:
        """Run until quit or ``max_frames`` is reached; return rendered frames."""

        frames = 0
        try:
            while self.running and (max_frames is None or frames < max_frames):
                self._handle_events()
                if not self.paused:
                    self.simulation.step()
                    if self.simulation.alive_population == 0:
                        self.paused = True
                        self.status_message = "All residents are gone. Press Space to restart."
                self._draw()
                self.pygame.display.flip()
                self.ui_clock.tick(self.frames_per_second)
                frames += 1
        finally:
            self.close()
        return frames

    def _handle_events(self) -> None:
        pygame = self.pygame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._select_at(event.pos)

    def _handle_key(self, key: int) -> None:
        pygame = self.pygame
        if key == pygame.K_SPACE:
            if self.simulation.game_over:
                self._restart()
            else:
                self.paused = not self.paused
                self.status_message = "Paused" if self.paused else "AI simulation running"
        elif key == pygame.K_UP:
            self.frames_per_second = min(60, self.frames_per_second + 3)
            self.status_message = f"Simulation speed: {self.frames_per_second} ticks/sec"
        elif key == pygame.K_DOWN:
            self.frames_per_second = max(2, self.frames_per_second - 3)
            self.status_message = f"Simulation speed: {self.frames_per_second} ticks/sec"

    def _restart(self) -> None:
        self.simulation = ColonySimulation(self.simulation.config)
        self.selected_agent_id = None
        self.selected_settlement_id = "settlement-000"
        self.paused = False
        self.running = True
        self.status_message = "New deterministic run started"

    def _select_at(self, position: Tuple[int, int]) -> None:
        if not self._map_rect.collidepoint(position):
            return
        cell_width = self._map_rect.width / self.simulation.config.width
        cell_height = self._map_rect.height / self.simulation.config.height
        world_x = int((position[0] - self._map_rect.left) / cell_width)
        world_y = int((position[1] - self._map_rect.top) / cell_height)
        candidates = [
            agent
            for agent in self.simulation.alive_agents
            if abs(agent.x - world_x) <= 1 and abs(agent.y - world_y) <= 1
        ]
        if candidates:
            selected = min(candidates, key=lambda item: (abs(item.x - world_x) + abs(item.y - world_y), item.agent_id))
            self.selected_agent_id = selected.agent_id
            self.selected_settlement_id = selected.settlement_id
            self.status_message = f"Selected {selected.agent_id}"

    def _draw(self) -> None:
        self.screen.fill(BACKGROUND)
        self._draw_map()
        self._draw_panel()

    def _draw_map(self) -> None:
        pygame = self.pygame
        rect = self._map_rect
        pygame.draw.rect(self.screen, (23, 33, 37), rect)
        cell_width = rect.width / self.simulation.config.width
        cell_height = rect.height / self.simulation.config.height
        territory_surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        for index, settlement in enumerate(sorted(self.simulation.settlements.values(), key=lambda item: item.settlement_id)):
            color = COLONY_COLORS[index % len(COLONY_COLORS)]
            for position in settlement.territory:
                x, y = (int(value) for value in position.split(","))
                cell = pygame.Rect(int(x * cell_width), int(y * cell_height), max(1, int(cell_width)), max(1, int(cell_height)))
                pygame.draw.rect(territory_surface, (*color, 35), cell)
        self.screen.blit(territory_surface, rect.topleft)
        for x in range(self.simulation.config.width + 1):
            px = rect.left + int(x * cell_width)
            pygame.draw.line(self.screen, GRID, (px, rect.top), (px, rect.bottom), 1)
        for y in range(self.simulation.config.height + 1):
            py = rect.top + int(y * cell_height)
            pygame.draw.line(self.screen, GRID, (rect.left, py), (rect.right, py), 1)
        for position, resource in sorted(self.simulation.resources.items()):
            x, y = (int(value) for value in position.split(","))
            center = (rect.left + int((x + 0.5) * cell_width), rect.top + int((y + 0.5) * cell_height))
            pygame.draw.rect(self.screen, RESOURCE_COLORS.get(resource, MUTED), (*center, 7, 7))
        for index, agent in enumerate(sorted(self.simulation.alive_agents, key=lambda item: item.agent_id)):
            color = COLONY_COLORS[sorted(self.simulation.settlements).index(agent.settlement_id) % len(COLONY_COLORS)]
            center = (rect.left + int((agent.x + 0.5) * cell_width), rect.top + int((agent.y + 0.5) * cell_height))
            radius = 5 if agent.age < self.simulation.config.adult_age else 8
            pygame.draw.circle(self.screen, color, center, radius)
            if agent.pregnancy_remaining is not None:
                pygame.draw.circle(self.screen, (255, 230, 120), center, radius + 3, 1)
            if agent.bond_partner_id:
                pygame.draw.circle(self.screen, (255, 170, 220), center, radius + 1, 1)
            if agent.agent_id == self.selected_agent_id:
                pygame.draw.circle(self.screen, TEXT, center, radius + 4, 2)
        title = self.title_font.render("COLONY WORLD", True, TEXT)
        self.screen.blit(title, (rect.left + 12, rect.top + 10))

    def _draw_panel(self) -> None:
        pygame = self.pygame
        rect = self._panel_rect
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=6)
        x = rect.left + 14
        y = rect.top + 12
        self._text("SIMULATION", x, y, self.title_font)
        y += 30
        invariants = self.simulation.invariants()
        y = self._text(f"tick {self.simulation.tick}   {'PAUSED' if self.paused else 'RUNNING'}", x, y)
        y = self._text(f"residents {self.simulation.alive_population}/{len(self.simulation.agents)}   money {invariants['total_money']}", x, y)
        learning_status = "ON" if self.simulation.config.ai_enabled else "OFF"
        y = self._text(f"AI learning: {learning_status}  |  policy: neural network  |  child: small dot  |  bond: pink ring", x, y, self.small_font, MUTED)
        y += 7
        self._draw_rule(x, y, rect.right - 14)
        y += 8
        self._text("SETTLEMENT LEDGER", x, y, self.font)
        y += 22
        for index, settlement in enumerate(sorted(self.simulation.settlements.values(), key=lambda item: item.settlement_id)):
            color = COLONY_COLORS[index % len(COLONY_COLORS)]
            population = sum(1 for agent in self.simulation.alive_agents if agent.settlement_id == settlement.settlement_id)
            y = self._text(f"{settlement.settlement_id}  people {population}  treasury {settlement.treasury}", x, y, color=color)
            y = self._text(f"  goods: {self._short_dict(settlement.storage, 64)}", x, y, self.small_font, MUTED)
            y = self._text(f"  demand: {self._short_dict(settlement.demand, 64)}  tech: {','.join(settlement.technologies) or '-'}", x, y, self.small_font, MUTED)
        y += 5
        self._draw_rule(x, y, rect.right - 14)
        y += 8
        selected = self.simulation.agents.get(self.selected_agent_id) if self.selected_agent_id else None
        self._text("RESIDENT INSPECTOR", x, y, self.font)
        y += 22
        if selected is None:
            y = self._text("Click a resident on the map to inspect it.", x, y, self.small_font, MUTED)
        else:
            y = self._text(f"{selected.agent_id}  {selected.sex}  age {selected.age}  {selected.settlement_id}", x, y, self.small_font)
            y = self._text(f"health {selected.health}  hunger {selected.hunger}  energy {selected.energy}", x, y, self.small_font, MUTED)
            y = self._text(f"wallet {selected.wallet}  bond {selected.bond_partner_id or '-'}  children {len(selected.children)}", x, y, self.small_font, MUTED)
            y = self._text(f"memory {len(selected.memory)}/{self.simulation.config.memory_capacity}  learned {self._short_dict(selected.learned_policy, 54) or '-'}", x, y, self.small_font, MUTED)
            last_decision = next(
                (
                    event
                    for event in reversed(self.simulation.events)
                    if event.event_type == "agent_decision" and event.payload.get("agent_id") == selected.agent_id
                ),
                None,
            )
            last_learning = next(
                (
                    event
                    for event in reversed(self.simulation.events)
                    if event.event_type == "learning_updated" and event.payload.get("agent_id") == selected.agent_id
                ),
                None,
            )
            if last_decision is not None and last_learning is not None:
                y = self._text(
                    f"AI chose {last_decision.payload.get('action')}  reward {last_learning.payload.get('reward')}  value {last_learning.payload.get('value')}",
                    x,
                    y,
                    self.small_font,
                    (180, 230, 190),
                )
            if selected.job_id and selected.job_id in self.simulation.production_jobs:
                job = self.simulation.production_jobs[selected.job_id]
                total = max(1, job.remaining_ticks + max(0, self.simulation.tick - job.started_tick))
                completed = max(0, total - job.remaining_ticks)
                y = self._text(f"training {job.recipe_name}: {completed}/{total} labor ticks", x, y, self.small_font, (255, 220, 140))
                self._draw_progress(x, y, rect.right - 14, completed / total)
                y += 13
            else:
                y = self._text("training: idle (AI chooses the next work)", x, y, self.small_font, MUTED)
        y += 5
        self._draw_rule(x, y, rect.right - 14)
        y += 8
        self._text("ACTIVE WORK", x, y, self.font)
        y += 22
        if not self.simulation.production_jobs and not self.simulation.research_jobs:
            y = self._text("No active work. AI is evaluating needs.", x, y, self.small_font, MUTED)
        for job in sorted(self.simulation.production_jobs.values(), key=lambda item: item.job_id)[:4]:
            total = max(1, job.remaining_ticks + max(0, self.simulation.tick - job.started_tick))
            completed = max(0, total - job.remaining_ticks)
            y = self._text(f"{job.agent_id}  {job.recipe_name}  {completed}/{total} ticks", x, y, self.small_font, TEXT)
            self._draw_progress(x, y, rect.right - 14, completed / total)
            y += 13
        for job in sorted(self.simulation.research_jobs.values(), key=lambda item: item.job_id)[:2]:
            y = self._text(f"{job.agent_id}  research {job.technology}  {job.remaining_ticks} ticks left", x, y, self.small_font, (170, 220, 255))
        y += 5
        self._draw_rule(x, y, rect.right - 14)
        y += 8
        self._text("CONTROLS", x, y, self.font)
        y += 22
        controls = "Space pause / continue | Up faster | Down slower\nAI controls movement, work, learning, love, trade, diplomacy, and conflict."
        for line in controls.splitlines():
            y = self._text(line, x, y, self.small_font, MUTED)
        y += 5
        y = self._text(self.status_message, x, y, self.small_font, (255, 220, 140))
        y += 8
        self._draw_rule(x, y, rect.right - 14)
        y += 8
        self._text("ACTIVITY (observations hidden)", x, y, self.font)
        y += 22
        visible_events = [
            event for event in self.simulation.events
            if event.event_type not in {"observation_recorded", "tick_advanced"}
        ]
        for event in visible_events[-7:]:
            payload = self._short_dict(event.payload, limit=52)
            y = self._text(f"{event.tick:>4} {event.event_type} {payload}", x, y, self.small_font, MUTED)

    def _draw_rule(self, x: int, y: int, right: int) -> None:
        self.pygame.draw.line(self.screen, GRID, (x, y), (right, y), 1)

    def _draw_progress(self, x: int, y: int, right: int, fraction: float) -> None:
        pygame = self.pygame
        width = max(20, right - x)
        background = pygame.Rect(x, y, width, 7)
        foreground = pygame.Rect(x, y, max(1, int(width * max(0.0, min(1.0, fraction)))), 7)
        pygame.draw.rect(self.screen, (55, 67, 75), background, border_radius=3)
        pygame.draw.rect(self.screen, (100, 210, 140), foreground, border_radius=3)

    def _text(self, value: str, x: int, y: int, font=None, color=TEXT) -> int:
        if font is None:
            font = self.font
        surface = font.render(str(value), True, color)
        self.screen.blit(surface, (x, y))
        return y + surface.get_height() + 2

    @staticmethod
    def _short_dict(value, limit: int = 58) -> str:
        text = ",".join(f"{key}={item}" for key, item in sorted(value.items()))
        return (text[: limit - 1] + "…") if len(text) > limit else text


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Pygame colony simulation UI")
    parser.add_argument("--frames", type=int, default=None, help="stop after a bounded number of rendered frames")
    parser.add_argument("--seed", type=int, default=20260828)
    args = parser.parse_args(argv)
    if args.frames is not None and args.frames < 0:
        parser.error("--frames must be non-negative")
    simulation = ColonySimulation(
        ColonyConfig(seed=args.seed, width=40, height=28, population=12, settlement_count=2, ai_enabled=True)
    )
    PygameSimulationApp(simulation).run(max_frames=args.frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
