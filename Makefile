include .build_info

pyi=uv run pyinstaller
version=v$(BUILD_VERSION)

all: build pack

build:
	$(pyi) pixvg.spec

pack:
	if not exist bin mkdir bin
	xcopy .\dist\pixvg.exe .\bin\${BUILD_NAME}\\ /Y
	if not exist .versions mkdir .versions
	tar -cvf "./.versions/${BUILD_NAME}_${version}_${BUILD_PLATFORM}.zip" -C "./bin/" "${BUILD_NAME}"

clean:
	if exist build rd /s /q build
	if exist dist rd /s /q dist
	if exist bin rd /s /q bin