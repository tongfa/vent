SHELL:=/bin/bash

OSS=$(realpath ../buildroot-arm/)
FMK_DIR=$(OSS)/fmk
HOST_BUILDROOT_DIR=$(OSS)/buildroot-2013.05/output/host/usr/bin
REVENG_DIR=$(OSS)/reveng-1.1.2

TARGETGCC=$(HOST_BUILDROOT_DIR)/mipsel-buildroot-linux-uclibc-gcc

all: .check-prereqs IPCUpdateC_V.1.7.19.modded.bin

.check-prereqs:
	dpkg -l python-magic > /dev/null
	touch $@

include tenvisd/make.inc

V1.7_V.1.7.19.zip:
	wget http://apps.tenvis.com/Download/JPT3815W/2013/V1.7_V.1.7.19.zip

IPCUpdateC_V.1.7.19.bin: V1.7_V.1.7.19.zip
	unzip V1.7_V.1.7.19.zip

tmp/IPCUpdateC_V.1.7.19.uImage.bin: IPCUpdateC_V.1.7.19.bin
	echo oss $(OSS)
	echo binwalk $(BINWALK)
	mkdir -p tmp
	dd if=$^ bs=8 skip=1 of=$@.tmp
	dd if=$^ bs=8 skip=1 of=$@.tmp
	dd if=$@.tmp count=1 of=$@ bs=\
	$$(binwalk $^ | awk '/uImage header/ { sub(/.*image size: /, ""); print $$1 }')

tmp/IPCUpdateC_V.1.7.19.kernelromfs.bin: tmp/IPCUpdateC_V.1.7.19.uImage.bin
	dd if=$^ bs=64 skip=1 of=$@

fmk: tmp/IPCUpdateC_V.1.7.19.kernelromfs.bin
	$(FMK_DIR)/extract-firmware.sh $^

define LOGIN_SKIP_AUTH
EOF
EOF
endef
export LOGIN_SKIP_AUTH
.check-patched: | fmk
	rm fmk/rootfs/bin/login
	echo '#!/bin/sh' > fmk/rootfs/bin/login
	echo 'exec /bin/busybox ash' >> fmk/rootfs/bin/login
	chmod 755 fmk/rootfs/bin/login
	echo '#!/bin/sh' > fmk/rootfs/bin/cat
	echo "exec /bin/busybox sed -e''" >> fmk/rootfs/bin/cat
	chmod 755 fmk/rootfs/bin/cat
	(cd fmk/rootfs ; patch -p1 ) < tenvis_turn_on_telnetd.patch
	rm fmk/rootfs/etc_ro/web/IPCPlayerPlug.exe
	touch $@

IPCUpdateC_V.1.7.19.modded.bin: tenvisd/tenvisd_mipsel | .check-patched
	cp tenvisd/tenvisd_mipsel fmk/rootfs/usr/bin/
	$(FMK_DIR)/build-firmware.sh fmk # creates fmk/new-firmware.bin
	$(HOST_BUILDROOT_DIR)/mkimage -A mips -O linux -T kernel -C lzma -a 0x80000000 -e 0x8026a000 -n "Linux Kernel Image" -d fmk/new-firmware.bin tmp/$@.uImage
	printf "IPCM\3\0\0\0" | dd bs=8 of=tmp/$@.nocrc
	cat tmp/$@.uImage >> tmp/$@.nocrc
	$(REVENG_DIR)/reveng -c -m KERMIT -f tmp/$@.nocrc -S | python -c "import sys, struct; xin=sys.stdin.read().split(); sys.stdout.write(struct.pack('BB', *[int(x, base=16) for x in xin]))" > tmp/$@.csum
	[ "$$(ls -l tmp/$@.csum | awk '{ printf $$5 }')" = "2" ]
	cat tmp/$@.nocrc tmp/$@.csum > $@

clean:
	-rm -rf fmk
	-rm -rf tmp
	-rm .check-*
	-rm IPCUpdateC_V.1.7.19.modded.bin


