"""Tests for the native splat renderer used by the filter channels."""

from __future__ import annotations

import numpy as np

from plantpilot import splat, splat_render
from splat_fixture import room_ply


def solid_gaussians(colours, positions, alpha=1.0, sigma=0.05) -> splat_render.Gaussians:
    colours = np.asarray(colours, dtype=np.float64)
    positions = np.asarray(positions, dtype=np.float64)
    count = positions.shape[0]
    return splat_render.Gaussians(
        xyz=positions,
        scale=np.full((count, 3), sigma),
        rot=np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (count, 1)),
        rgb=colours,
        alpha=np.full(count, alpha),
    )


def test_a_gaussian_fills_its_centre_with_its_colour():
    gaussians = solid_gaussians([[1.0, 0.0, 0.0]], [[0.0, 0.0, 0.0]])
    camera = splat_render.Camera.look_at((0.0, 0.0, 3.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 64, 48)
    image = np.asarray(splat_render.render(gaussians, camera)).astype(int)
    centre = image[24, 32]
    assert centre[0] > 200 and centre[1] < 60 and centre[2] < 60
    assert image[2, 2].max() < 20  # far from the splat the background stays black


def test_the_upper_gaussian_lands_above_the_centre_with_y_up():
    gaussians = solid_gaussians([[1, 0, 0], [0, 1, 0]], [[0, 0, 0], [0, 1, 0]])
    camera = splat_render.Camera.look_at((0, 0, 3), (0, 0, 0), (0, 1, 0), 64, 48)
    image = np.asarray(splat_render.render(gaussians, camera)).astype(int)
    red = np.argwhere((image[:, :, 0] > 180) & (image[:, :, 1] < 80))
    green = np.argwhere((image[:, :, 1] > 180) & (image[:, :, 0] < 80))
    assert red.size and green.size
    assert green[:, 0].mean() < red[:, 0].mean()  # row index grows downwards


def test_flipping_the_camera_up_vector_flips_the_image():
    gaussians = solid_gaussians([[1, 0, 0], [0, 1, 0]], [[0, 0, 0], [0, 1, 0]])
    right_way = splat_render.Camera.look_at((0, 0, 3), (0, 0, 0), (0, 1, 0), 64, 48)
    flipped = splat_render.Camera.look_at((0, 0, 3), (0, 0, 0), (0, -1, 0), 64, 48)

    def rows(image, channel):
        mask = image[:, :, channel] > 180
        return float(np.argwhere(mask)[:, 0].mean())

    one = np.asarray(splat_render.render(gaussians, right_way)).astype(int)
    other = np.asarray(splat_render.render(gaussians, flipped)).astype(int)
    # upright: green (at +y) is above red (at the origin); flipped: below it
    assert rows(one, 1) < rows(one, 0)
    assert rows(other, 1) > rows(other, 0)


def test_overlapping_semi_transparent_gaussians_accumulate_towards_opaque():
    gaussians = solid_gaussians([[0.2, 0.4, 0.9]] * 4, [[0.0, 0.0, 0.0]] * 4, alpha=0.4, sigma=0.08)
    camera = splat_render.Camera.look_at((0, 0, 3), (0, 0, 0), (0, 1, 0), 48, 32)
    image = np.asarray(splat_render.render(gaussians, camera)).astype(int)
    covered = 1.0 - (1.0 - 0.4) ** 4  # four layers of the same colour over black
    expected = np.array([0.2, 0.4, 0.9]) * 255 * covered
    assert np.allclose(image[16, 24], expected, atol=25)
    assert image[16, 24].sum() > 300  # a surface, not a faint dot


def test_a_camera_keeps_a_scene_up_axis_of_minus_y(tmp_path):
    # a capture whose up is -y: an object at world +y has to render below centre
    gaussians = solid_gaussians([[0.0, 1.0, 0.0]], [[0.0, 1.0, 0.0]])
    camera = splat_render.Camera.look_at((0, 0, 3), (0, 0, 0), (0, -1, 0), 64, 48)
    image = np.asarray(splat_render.render(gaussians, camera)).astype(int)
    green = np.argwhere(image[:, :, 1] > 180)
    assert green.size and green[:, 0].mean() > 24


def test_a_big_fog_gaussian_can_be_culled():
    gaussians = solid_gaussians([[1.0, 1.0, 1.0]], [[0.0, 0.0, 0.0]], sigma=0.5)
    camera = splat_render.Camera.look_at((0, 0, 3), (0, 0, 0), (0, 1, 0), 48, 32)
    kept = np.asarray(splat_render.render(gaussians, camera, max_gaussian_size=None)).astype(int)
    culled = np.asarray(splat_render.render(gaussians, camera, max_gaussian_size=0.1)).astype(int)
    assert kept.sum() > 0
    assert culled.sum() == 0


def test_from_scene_reads_the_artifact_and_keeps_a_deterministic_subset(tmp_path):
    out = tmp_path / "scene.npz"
    splat.ingest(room_ply(tmp_path / "room.ply"), out, hash_source=False)
    scene = splat.load_scene(out)
    gaussians = splat_render.from_scene(scene, maximum=500)
    assert len(gaussians) == 500
    again = splat_render.from_scene(scene, maximum=500)
    assert np.array_equal(gaussians.xyz, again.xyz)
    assert np.allclose(np.linalg.norm(gaussians.rot, axis=1), 1.0)


def test_from_scene_tolerates_a_version_one_artifact(tmp_path):
    old = tmp_path / "old.npz"
    np.savez(
        old,
        xyz=np.array([[0.0, 0.0, 0.0]]),
        rgb=np.array([[255, 0, 0]], dtype=np.uint8),
        size=np.full((1, 3), 0.05),
        alpha=np.array([1.0]),
        meta=np.array('{"frame": {"up_axis": "+y", "up_axis_index": 1, "up_axis_sign": 1}}'),
    )
    scene = splat.load_scene(old)
    gaussians = splat_render.from_scene(scene)
    assert np.allclose(gaussians.rot, [1.0, 0.0, 0.0, 0.0])
