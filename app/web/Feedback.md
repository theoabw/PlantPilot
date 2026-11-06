# Feedback for commit dc258d1055f7fef1148c48c1bf4f77f35b549663

1. The view controls should be more easily recognized and connected to the scene ui

2. Change the UI so that there is better integration between the scene and the three.js scene. The info sections could be collapsed by default and show as a sidebar when a button is pressed. For narrow screens, an alternative menu layout can be implemented.

The goal of these changes is to make the rest of the UI feel more cohesive with the scene.

-----

# Feedback for commit eadb2c2b991e2dab0f12ac3ebfdac0ae8386c35d

1. Implement the use of this font (raleway) into the UI:

<style>
@import url('https://fonts.googleapis.com/css2?family=Raleway:ital,wght@0,100..900;1,100..900&display=swap');
</style>

The goal is to make the UI more professional and "industry"-like

2. The main header of the website is unecessary, it can be placed under an info section or hidden within the collapsed panel, the demo selector switches ontop of the demo scene container are also too prominent, stow them away in an elegant fashion.

3. You may modify the web Makefile targets such that they refer to pnpm instead of npm
