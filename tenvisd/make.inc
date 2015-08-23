
tenvisd/shell.o: tenvisd/shell.c  tenvisd/shell.h
	gcc -c -Wall tenvisd/shell.c -Wno-multichar -o $@

tenvisd/tenvisd_x86: tenvisd/main.c tenvisd/shell.o
	gcc tenvisd/main.c tenvisd/shell.o -Wall -Wno-multichar -o $@

tenvisd/tenvisd_x86d: tenvisd/main.c tenvisd/shell.o
	gcc -g tenvisd/main.c tenvisd/shell.o -Wall -Wno-multichar -o $@

tenvisd/shell.mipsel.o: tenvisd/shell.c  tenvisd/shell.h
	$(TARGETGCC) -c -Wall tenvisd/shell.c -Wno-multichar -o $@

tenvisd/tenvisd_mipsel: tenvisd/main.c tenvisd/shell.mipsel.o
	$(TARGETGCC) tenvisd/main.c tenvisd/shell.mipsel.o -Wall -Wno-multichar -static-libgcc -o $@

