#!./venv/Scripts/python

import io
import os
import sys
from typing import Iterable, Any
from dataclasses import dataclass
from pathlib import Path as OSPath

import click
import numpy as np
from PIL import Image

from Common.Timer import Timer
from TermUtils.term import *


APP = os.path.dirname(sys.argv[0])

info_format = Format(fg=FG.BLUE)
error_format = Format(fg=FG.YEL, bg=BG.RED, style=STYLE.BOLD)
ok_format = Format(fg=FG.GREEN, style=STYLE.ITALIC)
inverted_format = Format(style=STYLE.REVERSE)


#---------------------------------------------------------------------------------------------------


@dataclass
class Neighborhood:
    top: Any = None
    right: Any = None
    bottom: Any = None
    left: Any = None
    top_left: Any = None
    top_right: Any = None
    bottom_right: Any = None
    bottom_left: Any = None


def np_neumann_neighbors(matrix: np.ndarray, x: int, y: int):
    """
    = Returns: The `Neighborhood` object according to the Von Neumann neighborhood (4-neighborhood)
    """
    
    if matrix.ndim != 2:
        raise ValueError("Matrix must be 2-dimensional")
    
    height, width = np.array(matrix.shape) - 1
    
    if x > width or y > height or x < 0 or y < 0:
        raise ValueError("x and y must be positive and not bigger than the matrix sizes")
    
    neighborhood = Neighborhood()
    
    if y != 0:
        neighborhood.top = matrix[y-1][x]
    if x != width:
        neighborhood.right = matrix[y][x+1]
    if y != height:
        neighborhood.bottom = matrix[y+1][x]
    if x != 0:
        neighborhood.left = matrix[y][x-1]
        
    return neighborhood


def np_moore_neighbors(matrix: np.ndarray, x: int, y: int):
    """
    = Returns: The `Neighborhood` object according to the Moore neighborhood (8-neighborhood)
    """
    
    if matrix.ndim != 2:
        raise ValueError("Matrix must be 2-dimensional")
    
    height, width = np.array(matrix.shape) - 1
    
    if x > width or y > height or x < 0 or y < 0:
        raise ValueError("x and y must be positive and not bigger than the matrix sizes")
    
    neighborhood = np_neumann_neighbors(matrix, x, y)
    
    if x != 0 and y != 0:
        neighborhood.top_right = matrix[y-1][x-1]    
    if x != width and y != 0:
        neighborhood.top_left = matrix[y-1][x+1]
    if x != width and y != height:
        neighborhood.bottom_right = matrix[y+1][x+1]
    if x != 0 and y != height:
        neighborhood.bottom_left = matrix[y+1][x-1]

    return neighborhood
    

#---------------------------------------------------------------------------------------------------


class Color:
    """
    - RGBA Color
    """
    def __init__(self, r, g, b, a):
        if not all(c >= 0 and c <= 255 for c in (r, g, b, a)):
            raise ValueError(f"Not all rgba components are valid: ({r}, {g}, {b}, {a})")
        
        self.r = r
        self.g = g
        self.b = b
        self.a = a
        
    def to_hex(self):
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}{self.a:02x}"
    
    def __eq__(self, other):
        if type(other) != Color:
            return False
        
        if self.r == other.r and self.g == other.g and self.b == other.b and self.a == other.a:
            return True
        else:
            return False
        
    def __repr__(self):
        return f"Color({self.r}, {self.g}, {self.b}, {self.a})"


class Point2D:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        
    def __repr__(self):
        return f"Point2D({self.x}, {self.y})"
    
    def __eq__(self, other: "Point2D"):
        if not isinstance(other, Point2D):
            return False

        if self.x == other.x and self.y == other.y:
            return True
        else:
            return False
        
    def __hash__(self) -> int:
        """
        src: https://www.shadertoy.com/view/MdcfDj
        """
        return ((self.x * 1597334677) ^ (self.y * 3812015801) * 1597334677)

   
class Cartesian2D():
    """
    - 2D coordinate system
    """
    def __init__(self, wdith: int, height: int):
        self.width = wdith
        self.height = height
    
    @property
    def size(self):
        return self.width * self.height
    

class Pixel2D(Point2D):
    """
    - Colored 2D Point
    """
    def __init__(self, x: int, y: int,
                 color: Color):
        Point2D.__init__(self, x, y)
        self.color = color
        
    def __repr__(self):
        return f"Pixel2D({self.x}, {self.y}, {self.color}); "
        
        
class Point2DSet(Cartesian2D):
    """
    - Set of points in 2D cartesian space
    - Includes bitmask of the contained points
    """
    def __init__(self, width: int, height: int, points: Iterable[Point2D] = None):
        Cartesian2D.__init__(self, width, height)
        self.bitmask = np.zeros((height, width), dtype=np.int8)
        self.data = set()
        
        if points is not None:
            for point in points:
                self.add_point(point)
        
    def add_point(self, point: Point2D):
        try:  
            self.bitmask[point.y, point.x] = 1
            self.data.add(point)
        except IndexError:
            raise ValueError(f"{point} if out of bounds")
        
    def remove_point(self, point: Point2D):
        try:
            self.bitmask[point.y, point.x] = 0
            self.data.remove(point)
        except IndexError:
            raise ValueError(f"{point} if out of bounds")
        
    def has_point(self, point: Point2D):
        return point in self.data
    
    def __repr__(self):
        return f"Point2DSet({self.width}, {self.height}, points={self.data})"


class Color2DRegion(Point2DSet):
    def __init__(self, color: Color, width:int, height: int, points: Iterable[Point2D] = None):
        Point2DSet.__init__(self, width, height, points)
        self.color: Color = color

    def __repr__(self):
        return f"Color2DRegion({self.width}, {self.height}, {self.color}, points={self.data})"
    

class Node2D(Point2D):
    """
    - 2D Point connected to some other 2D Points [Very similar to Doubly Linked List]
    """
    def __init__(self, x: int, y: int, next: "Node2D" = None, prev: "Node2D" = None):
        Point2D.__init__(self, x, y)
        self.next: Node2D = next
        self.prev: Node2D = prev
                
    def __repr__(self):
        next = self.next
        next_repr = "None" if next is None else f"{next.__class__.__name__}({next.x}, {next.y})"
        prev = self.prev
        prev_repr = "None" if prev is None else f"{prev.__class__.__name__}({prev.x}, {prev.y})"
        return f"Node2D({self.x}, {self.y}, next={next_repr}, prev={prev_repr})"
    

class VirtualNode2D(Point2D):
    """
    - Simply - it is a 2D point containing other 2D nodes
    - Complexly - see `Node2DGrid.connect()` behavior and this Class to understand how it is used
    """
    def __init__(self, x: int, y: int, real_nodes: tuple[Node2D, Node2D] = None):
        Point2D.__init__(self, x, y)
        self.real_nodes = real_nodes if real_nodes is not None else (None, None)
        self.state = 0
        
    @property
    def current(self):
        current = self.real_nodes[self.state]
        return current
    
    @property
    def next(self):
        return self.current.next
    
    @next.setter
    def next(self, val):
        self.current.next = val
        
    @property
    def prev(self):
        return self.current.prev
    
    @prev.setter
    def prev(self, val):
        self.current.prev = val
                           
    def flip(self):
        self.state = 0 if self.state else 1
    
    def __repr__(self):
        return f"VirtualNode2D({self.x}, {self.y}, {self.real_nodes}"
        
        
class NodeGrid2D(Cartesian2D):
    def __init__(self, width: int, height: int):
        Cartesian2D.__init__(self, width, height)
        self.data = [[Node2D(x, y) for x in range(self.width)] for y in range(self.height)]

    def top_left_of(self, x: int, y: int):
        return self.data[y][x]
    
    def top_right_of(self, x: int, y: int):
        return self.data[y][x+1]
    
    def bottom_right_of(self, x: int, y: int):
        return self.data[y+1][x+1]
    
    def bottom_left_of(self, x: int, y: int):
        return self.data[y+1][x]
    
    def connect(self, node_1: Node2D, node_2: Node2D):
        """
        - If we connect node, which is already connected (or connect to node, which is already connected),
        this node will be turned into a virtual node.
        """
        if node_1.prev is not None and node_1.next is not None:
            virtual_node = VirtualNode2D(node_1.x, node_1.y)
            virtual_node.real_nodes = (Node2D(node_1.x, node_1.y, node_1.next, node_1.prev), Node2D(node_1.x, node_1.y))
            virtual_node.prev.next = virtual_node.current
            virtual_node.next.prev = virtual_node.current
            virtual_node.flip()
            virtual_node.next = node_2.current if type(node_2) == VirtualNode2D else node_2
            node_1 = virtual_node.current
            self.data[node_1.y][node_1.x] = virtual_node
            
        if node_2.prev is not None and node_2.next is not None:
            virtual_node = VirtualNode2D(node_2.x, node_2.y)
            virtual_node.real_nodes = (Node2D(node_2.x, node_2.y, node_2.next, node_2.prev), Node2D(node_2.x, node_2.y))
            virtual_node.prev.next = virtual_node.current
            virtual_node.next.prev = virtual_node.current
            virtual_node.flip()
            virtual_node.prev = node_1.current if type(node_1) == VirtualNode2D else node_1
            node_2 = virtual_node.current
            self.data[node_2.y][node_2.x] = virtual_node    
        
        node_1.next = node_2.current if type(node_2) == VirtualNode2D else node_2
        node_2.prev = node_1.current if type(node_1) == VirtualNode2D else node_1

    def __repr__(self):
        return f"NodeGrid2D({self.width}, {self.height})"
    
    def __str__(self):
        return f"NodeGrid2D({self.width}, {self.height}); Data={self.data}"


class NodeLoop:
    class IsNotEnclosed(Exception):
        ...
    
    def __init__(self, origin: Node2D, trust: bool = False):
        self.origin = origin
        if not trust:
            if not self.is_enclosed():
                raise NodeLoop.IsNotEnclosed
            
    def optimize(self):
        """
        - Delete unnecessary points
        
        Example:
        
        x - x - x 
        
        x - - - x 
        """
        origin = self.origin
        node = origin
        while True:
            if node.next.x == node.prev.x or node.next.y == node.prev.y:
                node.prev.next = node.next
                node.next.prev = node.prev
            
            node = node.next
            
            if node == origin:
                break
          
    def is_enclosed(self): 
        if self.origin.next == None:
            return False
        
        node = self.origin.next
        while node.next != None and node != self.origin:
            node = node.next

        if node == self.origin:
            return True
        else:
            return False
              
    def __repr__(self):
        return f"NodeLoop(origin={self.origin})"


@dataclass
class SVGPath:
    data: str
    color: str


class SVG:
    def __init__(self, width: int, height: int, scale: int):
        self.paths: list[SVGPath] = []
        self.width = width
        self.height = height
        self.scale = scale
        
    def _m(self, node: Node2D):
        """
        - Generate svg M (moveto command) for the given node
        """
        return f"M{node.x * self.scale},{node.y * self.scale}"
    
    def _l(self, node: Node2D):
        """
        - Generate svg L (lineto command) for the given node
        """
        return f"L{node.x * self.scale},{node.y * self.scale}"
    
    def _z(self):
        """
        - Return Z. Just Z
        """
        return "Z"
    
    def build_paths(self):
        path_str = ""
        for path_svg in self.paths:
            path_str += f'<path d="{path_svg.data}" fill="{path_svg.color}" />\n'
        return path_str
         
    def loop_to_path_data(self, node_loop: NodeLoop):
        origin = node_loop.origin
        node = origin
        path_data = f"{self._m(origin)}"
        while node.next != origin:
            node = node.next
            path_data += f"{self._l(node)}"
        
        path_data += self._z()
        
        return path_data        

    def add_path(self, path: SVGPath):
        self.paths.append(path)
    
    def build_svg(self):
        svg = ('<svg version="1.1" xmlns="http://www.w3.org/2000/svg" '
               f'width="{self.width * self.scale}" height="{self.height * self.scale}" shape-rendering="crispEdges">\n')
        
        svg += self.build_paths()
            
        svg += '</svg>'
        
        return svg
   

 #---------------------------------------------------------------------------------------------------
 
 
def get_distinct_color_regions(img: Image):
    img_matrix = np.array(img)
    
    known_colors = set()
    regions: dict[Color2DRegion] = {}
    
    for y, row, in enumerate(img_matrix):
        for x, pixel in enumerate(row):
            pix_hex = Color(*pixel).to_hex()
            if pix_hex not in known_colors:
                known_colors.add(pix_hex)
                regions[pix_hex] = Color2DRegion(Color(*pixel), *img.size)
                
            regions[pix_hex].add_point(Point2D(x, y))
        
    return list(regions.values())


def find_connected_neumann_regions(bitmask: np.ndarray):
    """
    - Acts as scikit (skimage) measurement.label function with connectivity=1
    
    See
    ---
    https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.label
    """
    regions = np.zeros_like(bitmask)
    region_id = 1
    stack = []

    rows, cols = bitmask.shape

    for y in range(rows):
        for x in range(cols):
            if bitmask[y, x] == 1 and regions[y, x] == 0:
                stack.append((x, y))

                while stack:
                    x, y = stack.pop()
                    if regions[y, x] != 0:
                        continue
                    regions[y, x] = region_id
                    neighbors = np_neumann_neighbors(bitmask, x, y)
                    
                    if neighbors.top == 1:
                        stack.append((x, y - 1))
                        
                    if neighbors.right == 1:
                        stack.append((x + 1, y))
                        
                    if neighbors.bottom == 1:
                        stack.append((x, y + 1))
                        
                    if neighbors.left == 1:
                        stack.append((x - 1, y))

                region_id += 1

    return regions


def split_into_clusters(region: Color2DRegion):
    """
    - Cluster - connected area of pixels according to the Von Neumann neighborhood
    """
    cluster_matrix = find_connected_neumann_regions(region.bitmask)
    
    known_clusters = set()
    clusters: dict[Color2DRegion] = {}
    
    for y, row in enumerate(cluster_matrix):
        for x, id in enumerate(row):
            if id == 0:
                continue
            
            if id not in known_clusters:
                known_clusters.add(id)
                clusters[id] = Color2DRegion(region.color, region.width, region.height)
                
            clusters[id].add_point(Point2D(x, y))
                        
    return list(clusters.values())


def trace_bitmask(bitmask: np.ndarray):
    """
    - Trace the edges for the given bitmask
    """
    
    #? This function can work well with bitmask from both `split_into_clusters`
    #? and `get_distinct_color_regions` functions output
    
    #! but `extract_node_loops` will behave incorrectly if we skip `split_into_clusters`
    #! due to Virtual Nodes.
    #! It can be fixed at the `extract_node_loop` side, but I don't know how for now
    
    #~ In this case, we will create loops that are the same loop but from different origin points.
    
    height, width = bitmask.shape
     
    node_grid = NodeGrid2D(width+1, height+1)
    
    for y in range(height):
        for x in range(width):
            if bitmask[y][x] == 1:
                neighbors = np_neumann_neighbors(bitmask, x, y)
                
                #? Construct the pixel edges clockwise
                
                #! Clockwise or counter clockwise direction is important for the
                #! future svg conversion
                
                #~ Inner areas will be naturally traced counter clockwise
                #~ Controversial intersection nodes will be convered to 
                #~ Virtual nodes
                
                if neighbors.top in (0, None):
                    node_grid.connect(node_grid.top_left_of(x, y), node_grid.top_right_of(x, y))
                    
                if neighbors.right in (0, None):
                    node_grid.connect(node_grid.top_right_of(x, y), node_grid.bottom_right_of(x, y))
                    
                if neighbors.bottom in (0, None):
                    node_grid.connect(node_grid.bottom_right_of(x, y), node_grid.bottom_left_of(x, y))
                    
                if neighbors.left in (0, None):
                    node_grid.connect(node_grid.bottom_left_of(x, y), node_grid.top_left_of(x, y))
                           
    return node_grid
    
        
def extract_node_loops(node_grid: NodeGrid2D):
    node_loops = []
    visited = set()
    for row in node_grid.data:
        for node in row:
            if node.next != None and node not in visited:
                
                #? We have to check is loop enclosed or not manually
                #? beacuse we also need to track visited nodes
                
                origin = node
                node = node.next
                while node.next != None and node != origin:
                    visited.add(node)
                    node = node.next
    
                if node == origin:
                    node_loops.append(NodeLoop(node, True))  
                else:
                    raise NodeLoop.IsNotEnclosed 
    
    return node_loops


#---------------------------------------------------------------------------------------------------


@click.command()
@click.option("-s", "--scale", default=1, help="Apply scale to all resulted SVGs, images will not be scaled")
def main(scale):   
    """
    This script pixel perfectly traces pixel sprites to SVG vector images
    
        - <./in> - input folder
        - <./out> - output folder
    """
    os.chdir(APP)
    os.makedirs("in", exist_ok=True)
    os.makedirs("out", exist_ok=True)
    
    if scale < 1:
        writef(":: Scale is too low ::", error_format)
        write()
        input("Press Enter to exit...")
        Scr.reset_mode()
        sys.exit(1)
    
    input_files = set(os.listdir('./in'))
    png_files = set(filter(lambda f: 
        f.endswith(".png"), input_files))
    other_files = input_files - png_files
    
    if len(png_files) == 0:
        set_format(error_format)
        write("No input files!\n")
        input("Press Enter to exit...")
        Scr.reset_mode()
        sys.exit(1)
        
    writef("< FILES >", inverted_format)
    write()
    [write(f"\t{ffg('>', FG.GREEN)} {file} - {ffg('[ok]', FG.GREEN)}\n") for file in png_files]
    [write(f"\t{ffg('>', FG.RED)} {file} - {ffg('[skip]', FG.RED)}") for file in other_files]
    write()
    
    
    with Timer(fstyle("Total", STYLE.BOLD)):
        for file in png_files:
            image: Image = None
            
            write(f"{fstyle(':: filename:', STYLE.BOLD)} {ffg(file, FG.MAGNT)}\n")
            
            try:
                with open(f"./in/{file}", 'rb') as file_img:
                    image = Image.open(io.BytesIO(file_img.read()))
            except Exception as e:
                writef(f":: File error: {e} ::", error_format)
                write()
                write(f"{ffg('>> SKIP', FG.RED)}\n")
                continue
                   
            image = image.convert("RGBA")   
                         
            width, height = image.size       
                
            write(f"\timage size: {ffg(width, FG.BLUE)}x{ffg(height, FG.BLUE)}\n")
            write(f"\tscale: {ffg(scale, FG.BLUE)}\n") 
            
            write()
                
            with Timer(fstyle(file, STYLE.BOLD)) as timer:  
                svg = SVG(*image.size, scale=scale)
                
                timer.tic()
                write(f"\t┌ Splitting image into distinct {ffg('color regions', FG.CYAN)}...\n")
                color_regions: list[Color2DRegion] = [r for r in get_distinct_color_regions(image) if r.color.a == 255]
                write(f"\t│ {ffg(len(color_regions), FG.CYAN)} color region\s\n")
                writef(f"\t└ Done: {timer.toc():.2f}s\n", ok_format)
                
                timer.tic()
                write(f"\t┌ Extracting {ffg('pixel clusters', FG.YEL)} from the {ffg('color regions', FG.CYAN)}...\n")
                cluster_groups: list[Color2DRegion] = [cluster for region in color_regions for cluster in split_into_clusters(region)]
                write(f"\t│ {ffg(len(cluster_groups), FG.YEL)} cluster\s\n")
                writef(f"\t└ Done: {timer.toc():.2f}s\n", ok_format)
                
                timer.tic()
                write(f"\t┌ {ffg('Pixel clusters', FG.YEL)} processing...\n")
                for cluster in cluster_groups:
                    traced_bitmask = trace_bitmask(cluster.bitmask)
                    node_loops = extract_node_loops(traced_bitmask)
                    [loop.optimize() for loop in node_loops]
                    svg.add_path(SVGPath(
                        ''.join(map(svg.loop_to_path_data, node_loops)),
                        cluster.color.to_hex()
                    ))
                    
                writef(f"\t└ Done: {timer.toc():.2f}s\n", ok_format)
                    
                filename = f"{OSPath(file).stem}_X{scale}.svg"
                with open(f'./out/{filename}', 'w') as svg_file:
                    write("\t┌ Saving...\n")
                    svg_file.write(svg.build_svg())
                    writef(f"\t└ Saved as {fstyle(filename, STYLE.BOLD)} [+]\n", ok_format)
                                
                write()
                
                
    writef("Done!\n", ok_format)
    input("Press Enter to exit...")
    
if __name__ == '__main__':
    os.system("color") #! NOT TESTED ON LINUX
    try:
        main()
    except Exception as e:
        writef(f"[ERROR: {e}]", error_format)
    except KeyboardInterrupt:
        input("Press Enter to exit...")
    Scr.reset_mode()