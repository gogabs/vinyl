"""Vinyl: audiolivros e música no R36S, com menus falados."""
import r36s_a11y as a11y

from vinyl.app import App

game = a11y.Game(fps=10, repeat=True)
App(game)
game.run()
