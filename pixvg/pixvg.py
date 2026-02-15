import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import click
import numpy as np
from numpy import typing as npt
from PIL import Image
from rich import box
from rich.console import Console
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

APP_PATH = Path(sys.argv[0]).parent
IN_FOLDER = APP_PATH / "in"
OUT_FOLDER = APP_PATH / "out"

MAX_SAFE_SIZE = 512
MAX_SAFE_COLORS = 128
ALLOWED_TYPES = (".png",)

console = Console(highlight=False)


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: int

    def to_hex(self):
        r, g, b, a = self.r, self.g, self.b, self.a
        return f"#{r:02x}{g:02x}{b:02x}{a:02x}"


@dataclass(frozen=True)
class Color2DRegion:
    color: Color
    offset: tuple[int, int]
    size: tuple[int, int]
    bitmask: npt.NDArray[np.bool]

    @property
    def dx(self):
        return self.offset[0]

    @property
    def dy(self):
        return self.offset[1]

    @property
    def w(self):
        return self.size[0]

    @property
    def h(self):
        return self.size[1]


class Node2D:
    def __init__(
        self,
        x: int,
        y: int,
        prev_node: Optional["Node2D"] = None,
        next_node: Optional["Node2D"] = None,
    ):
        self.pos = (x, y)
        self.prev: Optional[Node2D] = prev_node
        self.next: Optional[Node2D] = next_node

    @property
    def x(self):
        return self.pos[0]

    @property
    def y(self):
        return self.pos[1]

    def __str__(self):
        n = f"({self.next.x}, {self.next.y})" if self.next is not None else "..."
        p = f"({self.prev.x}, {self.prev.y})" if self.prev is not None else "..."
        return f"{p} <- Node2D({self.x}, {self.y}) -> {n}"


class VirtualNode2D:
    def __init__(self, x: int, y: int, nodes: tuple["Node2D", "Node2D"]):
        self.pos = (x, y)
        self.__nodes = nodes
        self.__direction: Literal[0, 1] = 0

    @classmethod
    def from_node(cls, base: Node2D):
        state_0 = Node2D(base.x, base.y, base.prev, base.next)
        state_1 = Node2D(base.x, base.y)

        virtual = cls(*base.pos, nodes=(state_0, state_1))

        if state_0.prev is not None:
            state_0.prev.next = state_0

        if state_0.next is not None:
            state_0.next.prev = state_0

        return virtual

    @property
    def x(self):
        return self.pos[0]

    @property
    def y(self):
        return self.pos[1]

    @property
    def current(self):
        return self.__nodes[self.__direction]

    @property
    def next(self):
        return self.current.next

    @next.setter
    def next(self, node: Optional[Node2D]):
        self.current.next = node

    @property
    def prev(self):
        return self.current.prev

    @prev.setter
    def prev(self, node: Optional[Node2D]):
        self.current.prev = node

    def flip(self):
        self.__direction ^= 1

    def __repr__(self):
        return f"VirtualNode2D({self.x}, {self.y}, nodes={self.__nodes})"


class NodeGrid2D:
    def __init__(self, width: int, height: int, x_offset: int = 0, y_offset: int = 0):
        self.offset = (x_offset, y_offset)
        self.size = (width, height)
        self.__grid: list[list[Node2D | VirtualNode2D | None]] = [
            [Node2D(x + x_offset, y + y_offset) for x in range(width)]
            for y in range(height)
        ]
        self.__is_locked = False

    @property
    def dx(self):
        return self.offset[0]

    @property
    def dy(self):
        return self.offset[1]

    @property
    def w(self):
        return self.size[0]

    @property
    def h(self):
        return self.size[1]

    @property
    def is_locked(self):
        return self.__is_locked

    def __resolve(self, node):
        """Convert node to VirtualNode if needed, return what to use for connections"""
        if isinstance(node, VirtualNode2D):
            return node

        if node.prev is not None and node.next is not None:
            virtual = VirtualNode2D.from_node(node)
            local_y = node.y - self.dy
            local_x = node.x - self.dx
            self.__grid[local_y][local_x] = virtual
            virtual.flip()
            return virtual

        return node

    def get_grid_iter(self):
        return iter(self.__grid)

    def get_nodes_iter(self):
        for row in self.__grid:
            for node in row:
                if node is not None:
                    yield node

    def at(self, x: int, y: int):
        return self.__grid[y][x]

    def connect(
        self,
        node_src: Node2D | VirtualNode2D,
        node_dest: Node2D | VirtualNode2D,
    ):
        if self.__is_locked:
            raise RuntimeError("Cannot connect while locked")

        src = self.__resolve(node_src)
        dest = self.__resolve(node_dest)

        src.next = dest
        dest.prev = src

    def lock(self):
        if self.__is_locked:
            return 0

        removed = 0
        self.__is_locked = True
        for row in self.__grid:
            for idx, node in enumerate(row):
                if node.next is None and node.prev is None:
                    removed += 1
                    row[idx] = None

        return removed


class NodeLoop:
    class IsNotEnclosed(Exception):
        pass

    @staticmethod
    def is_enclosed(origin: Node2D):
        node = origin.next
        while node.next is not None and node != origin:
            node = node.next

        return node == origin

    def __init__(self, origin: Node2D):
        if not NodeLoop.is_enclosed(origin):
            raise self.IsNotEnclosed

        self.origin = origin

    def optimize(self):
        origin = self.origin
        node = origin
        count = 0

        while True:
            if node.next.x == node.prev.x or node.next.y == node.prev.y:
                node.prev.next = node.next
                node.next.prev = node.prev
                count += 1

            node = node.next

            if node == origin:
                break

        return count

    def visit_all(self):
        visited: set[Node2D] = set()
        visited.add(self.origin)

        node = self.origin.next
        while node != self.origin:
            visited.add(node)
            node = node.next

        return visited

    def __repr__(self):
        return f"NodeLoop(origin={self.origin})"


@dataclass(frozen=True)
class SVGPath:
    data: str
    color: Color


class SVG:
    def __init__(self, width: int, height: int, scale: int):
        self.paths: list[SVGPath] = []
        self.size = (width, height)
        self.scale = scale

    @property
    def w(self):
        return self.size[0]

    @property
    def h(self):
        return self.size[1]

    @staticmethod
    def __z():
        return "Z"

    def __m(self, node: Node2D):
        return f"M{node.x * self.scale},{node.y * self.scale}"

    def __l(self, node: Node2D):
        return f"L{node.x * self.scale},{node.y * self.scale}"

    def construct_path_segment(self, node_loop: NodeLoop):
        origin = node_loop.origin
        node = origin
        path_data = self.__m(origin)

        while node.next != origin:
            node = node.next
            path_data += self.__l(node)

        path_data += self.__z()

        return path_data

    def add_path_segment(self, path: SVGPath):
        self.paths.append(path)

    def build_svg(self):
        svg = (
            '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" '
            f'width="{self.w * self.scale}" height="{self.h * self.scale}" '
            'shape-rendering="crispEdges">\n'
        )

        for path in self.paths:
            svg += f'<path d="{path.data}" fill="{path.color.to_hex()}" />\n'

        svg += "</svg>"
        return svg


class App:
    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        scale: int,
        split_regions: bool,
        force: bool,
    ):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.scale = scale
        self.split_regions = split_regions
        self.force = force

    @staticmethod
    def split_into_regions(img: Image.Image) -> list[Color2DRegion]:
        np_img = np.array(img)
        unique_colors, inverse = np.unique(
            np_img.reshape(-1, 4), axis=0, return_inverse=True
        )
        regions = []

        for idx, color_arr in enumerate(unique_colors):
            if color_arr[3] != 255:
                continue

            mask = inverse.reshape(np_img.shape[:2]) == idx
            color = Color(*color_arr)
            regions.append(Color2DRegion(color, (0, 0), img.size, mask))

        return regions

    @staticmethod
    def find_connected(bitmask: npt.NDArray[np.bool]) -> npt.NDArray:
        regions = np.zeros_like(bitmask, dtype=np.int32)
        region_id = 1
        rows, cols = bitmask.shape

        stack = np.empty((rows * cols, 2), dtype=np.int32)
        stack_size = 0

        for y in range(rows):
            for x in range(cols):
                if bitmask[y, x] and regions[y, x] == 0:
                    stack[stack_size] = [x, y]
                    stack_size = 1

                    while stack_size > 0:
                        stack_size -= 1
                        cx, cy = stack[stack_size]

                        if regions[cy, cx] != 0:
                            continue

                        regions[cy, cx] = region_id

                        if cy > 0 and bitmask[cy - 1, cx] and regions[cy - 1, cx] == 0:
                            stack[stack_size] = [cx, cy - 1]
                            stack_size += 1

                        if (
                            cx < cols - 1
                            and bitmask[cy, cx + 1]
                            and regions[cy, cx + 1] == 0
                        ):
                            stack[stack_size] = [cx + 1, cy]
                            stack_size += 1

                        if (
                            cy < rows - 1
                            and bitmask[cy + 1, cx]
                            and regions[cy + 1, cx] == 0
                        ):
                            stack[stack_size] = [cx, cy + 1]
                            stack_size += 1

                        if cx > 0 and bitmask[cy, cx - 1] and regions[cy, cx - 1] == 0:
                            stack[stack_size] = [cx - 1, cy]
                            stack_size += 1

                    region_id += 1

        return regions

    @staticmethod
    def split_into_clusters(region: Color2DRegion) -> list[Color2DRegion]:
        cluster_matrix = App.find_connected(region.bitmask)
        max_id = int(np.max(cluster_matrix)) if cluster_matrix.size > 0 else 0
        clusters = []

        for cid in range(1, max_id + 1):
            mask = cluster_matrix == cid

            if not np.any(mask):
                continue

            rows_with_cluster = np.any(mask, axis=1)
            cols_with_cluster = np.any(mask, axis=0)

            y_indices = np.where(rows_with_cluster)[0]
            x_indices = np.where(cols_with_cluster)[0]

            y_min, y_max = y_indices[0], y_indices[-1]
            x_min, x_max = x_indices[0], x_indices[-1]

            cluster_bitmask = mask[y_min : y_max + 1, x_min : x_max + 1]

            clusters.append(
                Color2DRegion(
                    region.color,
                    (region.dx + x_min, region.dy + y_min),
                    (x_max - x_min + 1, y_max - y_min + 1),
                    cluster_bitmask,
                )
            )

        return clusters

    @staticmethod
    def trace_bitmask(
        bitmask: npt.NDArray, x_offset: int, y_offset: int
    ) -> tuple[NodeGrid2D, int]:
        height, width = bitmask.shape
        node_grid = NodeGrid2D(width + 1, height + 1, x_offset, y_offset)

        for y in range(height):
            for x in range(width):
                if not bitmask[y, x]:
                    continue

                if y == 0 or not bitmask[y - 1, x]:
                    node_grid.connect(node_grid.at(x, y), node_grid.at(x + 1, y))

                if x == width - 1 or not bitmask[y, x + 1]:
                    node_grid.connect(
                        node_grid.at(x + 1, y), node_grid.at(x + 1, y + 1)
                    )

                if y == height - 1 or not bitmask[y + 1, x]:
                    node_grid.connect(
                        node_grid.at(x + 1, y + 1), node_grid.at(x, y + 1)
                    )

                if x == 0 or not bitmask[y, x - 1]:
                    node_grid.connect(node_grid.at(x, y + 1), node_grid.at(x, y))

        removed_count = node_grid.lock()
        active_count = width * height - removed_count

        return node_grid, active_count

    @staticmethod
    def extract_node_loops(node_grid: NodeGrid2D) -> list[NodeLoop]:
        node_loops = []
        visited = set()

        for node in node_grid.get_nodes_iter():
            if node not in visited and node.next is not None:
                node_loop = NodeLoop(node)
                visited.update(node_loop.visit_all())
                node_loops.append(node_loop)

        return node_loops

    @staticmethod
    def print_color_palette(
        image: Image.Image, max_colors: int, width: int, height: int, left_pad: int
    ) -> None:
        colors = image.getcolors(maxcolors=max_colors + 1)
        total_slots = width * height

        if colors is None:
            colors_sorted = []
        else:
            colors_sorted = sorted(
                [(count, color) for count, color in colors if color[3] > 0],
                key=lambda c: c[0],
                reverse=True,
            )

        palette_text = Text()

        for i in range(total_slots):
            if i < len(colors_sorted):
                count, color = colors_sorted[i]
                r, g, b, _ = color
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                palette_text.append("█", style=hex_color)
            else:
                palette_text.append("░", style="grey11")

            if (i + 1) % width == 0 and i + 1 < total_slots:
                palette_text.append("\n")

        panel = Panel(
            palette_text,
            box.SQUARE,
            title="[bold]Palette[/bold]",
            title_align="left",
            border_style="dim",
            expand=False,
            padding=(0, 0),
        )
        padded = Padding(panel, (0, 0, 0, left_pad))

        console.print(padded)

    def process_png(self, png_path: Path) -> bool:
        console.print(f" [dim]>[/dim] [cyan]{png_path.name}[/cyan]")

        try:
            image = Image.open(png_path)
        except OSError:
            console.print(f"[red]error[/red] cannot open {png_path.name} as image")
            console.print_exception()
            return False

        image = image.convert("RGBA")
        width, height = image.size
        colors = image.getcolors(maxcolors=MAX_SAFE_COLORS + 1)
        num_colors = len(colors) if colors else "n/a"

        console.print(f"   size: {width}x{height}")
        console.print(f"   scale: x{self.scale}")
        console.print(f"   colors: {num_colors}")

        self.print_color_palette(
            image,
            max_colors=MAX_SAFE_COLORS,
            width=console.size.width // 4,
            height=4,
            left_pad=3,
        )

        if not self.force and (width * height > MAX_SAFE_SIZE**2):
            console.print(
                f"   [yellow]skip[/yellow] {png_path.name} is too large [red](>{MAX_SAFE_SIZE})[/red]"
            )
            return False

        if not self.force:
            if colors is None:
                console.print(
                    f"   [yellow]skip[/yellow] {png_path.name} has too many colors [red](>{MAX_SAFE_COLORS})[/red]"
                )
                return False

        file_start = time.time()
        svg = SVG(width, height, scale=self.scale)

        step_start = time.time()
        with console.status(
            "[dim]wait...[/dim]", spinner="line", spinner_style="magenta"
        ):
            regions = self.split_into_regions(image)

        console.print(
            f"   regions: {len(regions)} [dim]({time.time() - step_start:.2f}s)[/dim]"
        )

        if self.split_regions:
            step_start = time.time()
            clusters: list[Color2DRegion] = []
            with Live(
                Rule(characters="-", style="dim"),
                console=console,
                transient=True,
                refresh_per_second=10,
            ):
                with console.status(
                    "[dim]wait...[/dim]",
                    spinner="line",
                    spinner_style="green",
                    refresh_per_second=10,
                ) as status:
                    for r, region in enumerate(regions):
                        status.update(
                            f"[bold yellow]region[/bold yellow] "
                            f"{r + 1}/{len(regions)} "
                            f"[bold]{region.color.to_hex()}[/bold]"
                        )

                        clusters.extend(self.split_into_clusters(region))

            console.print(
                f"   clusters: {len(clusters)} [dim]({time.time() - step_start:.2f}s)[/dim]"
            )
        else:
            clusters = regions

        step_start = time.time()
        with Live(
            Rule(characters="-", style="dim"),
            console=console,
            transient=True,
            refresh_per_second=10,
        ):
            with console.status(
                "[dim]wait...[/dim]",
                spinner="line",
                spinner_style="cyan",
                refresh_per_second=10,
            ) as status:
                for c, cluster in enumerate(clusters):
                    status.update(
                        f"[bold cyan]cluster[/bold cyan] "
                        f"{c + 1}/{len(clusters)} "
                        f"[bold]{cluster.color.to_hex()}[/bold] "
                        f"[dim]{cluster.w}x{cluster.h} at ({cluster.dx:+}, {cluster.dy:+})[/dim]"
                    )

                    node_grid, active_count = self.trace_bitmask(
                        cluster.bitmask,
                        cluster.dx,
                        cluster.dy,
                    )
                    node_loops = self.extract_node_loops(node_grid)

                    paths = []
                    for loop in node_loops:
                        loop.optimize()
                        paths.append(svg.construct_path_segment(loop))

                    path_data = "".join(paths)
                    svg.add_path_segment(SVGPath(path_data, cluster.color))

        console.print(f"   traced [dim]({time.time() - step_start:.2f}s)[/dim]")

        svg_str = svg.build_svg()

        svg_syntax = Syntax(
            svg_str,
            "xml",
            line_numbers=True,
            line_range=(1, 5),
            background_color="black",
        )
        console.print(svg_syntax)

        filename = f"{png_path.stem}_x{self.scale}.svg"
        out_path = self.output_dir / filename
        with open(out_path, "w") as f:
            f.write(svg_str)

        console.print(
            f"   [green]done[/green] {filename} [dim]({time.time() - file_start:.2f}s)[/dim]"
        )

        return True

    def run(self):
        self.output_dir.mkdir(exist_ok=True)

        input_files = {f for f in self.input_dir.iterdir() if f.is_file()}
        png_files = {f for f in input_files if f.suffix in ALLOWED_TYPES}
        other_files = input_files - png_files

        if not png_files:
            console.print("no input files")
            raise click.Abort()

        console.print("[reverse]< FILES >[/reverse]")

        for f in png_files:
            console.print(f"[green] + [/green] {f.name}")
        for f in other_files:
            console.print(f"[red] - [/red] {f.name}")

        console.print()

        total_start = time.time()
        processed = 0
        skipped = 0

        for png in png_files:
            try:
                success = self.process_png(png)
                console.print()

                if success:
                    processed += 1
                else:
                    skipped += 1
            except Exception:
                console.print(f"[red]error[/red] failed to process {png.name}")
                console.print_exception(show_locals=True)
                console.print()
                skipped += 1

        total_time = time.time() - total_start

        console.print(
            f"[green]Successful: {processed} file(s)[/green] "
            f"[dim]*[/dim] "
            f"[yellow]Skipped: {skipped} file(s)[/yellow] "
            f"[dim]*[/dim] "
            f"{total_time:.1f}s"
        )


@click.command()
@click.option(
    "-i",
    "--input",
    "input_dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True),
    default=Path("./in"),
)
@click.option(
    "-o",
    "--output",
    "output_dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path("./out"),
)
@click.option(
    "-s",
    "--scale",
    type=click.IntRange(min=1),
    default=1,
)
@click.option("--split-regions/--remain-regions", default=True)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    default=False,
)
def main(input_dir, output_dir, scale, split_regions, force):
    app = App(input_dir, output_dir, scale, split_regions, force)
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console = Console(highlight=False)
        console.print(f"[yellow on red bold]CRITICAL: {e}[/yellow on red bold]")
        raise
