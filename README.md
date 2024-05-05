# PixVG

<p align="center">
  <img title="PixVG" src="./examples/Logo.png" alt="Logo.png">
</p>
  
# About

**PixVG** is a small **CLI utility** for tracing pixel-style art/sprites/logos/icons to SVG. It optimizes the resulting SVG, so that every connected color region *(Connected in terms of Von Neumann neighborhood or 4-neighborhood)* will be separated from others.

Its intended to be used in **pixel-style ( web ) design** , as it works very well with duotone logos, icons and other elements where you can find farily large areas of connected colors *( For pixel art )*. Of course, You can easily colorize duotone SVGs later, for example, using CSS. So it is a flexible approach. Scaling pixel-style stuff is often problematic, but SVGs are easily scalable.

However, for real pixel art with many colors and a large number of small pixel clusters, PixVG will result in relatively heavy SVG files. It is **NOT** a magical tool.

Hope it will help you!



# Ver 1.0

``` bash
# Supports [-s int] [--scale int] command line arguemnt: apply scale to resulted SVGs.
$ pixvg -s 2
# or
$ pixvg --scale 2

# Input and Output folders are created automatically after the first launch
# <./in> - input folder
# <./out> - output folder
```

> **Note**
> 
> - Transparent pixels will be ignored
> - Max image size 512x512 px (Softlock, see the sources)
> - Supports only .png files (Softlock, see the sources)


### Dependency

1. numpy
2. pillow
3. click

> _Builded with python 3.11.1 on Win10 x64 via pyinstaller_


# Examples

### 1. Console output:

<p align="center">
  <img title="Terminal output" src="./examples/cmd.png" alt="cmd.png" width="600px">
</p>
 

### 2. Comparison with Aseprite:

<p align="center">
  <img title="Aseprite comparison" src="./examples/png_to_svg.png" alt="png_to_svg.png" width="600px">
</p>
