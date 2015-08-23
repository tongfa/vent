

function splitsh() {
    dd if=$1 bs=8 count=1 of=$1.preamble
    dd if=$1 bs=8 skip=1 of=$1.preamble.remain

    uImageSize=$(binwalk $1.preamble.remain | awk '/uImage header/ {printf $20}')
    dd if=$1.remain bs=$((64 + $uImageSize)) count=1 of=$1.uImage
    dd if=$1.remain bs=$((64 + uImageSize)) skip=1 of=$1.uImage.remain

    head --bytes -2 $1 > $1.m2
    tail --bytes +4 $1 > $1.m2.plus4
    tail --bytes +8 $1 > $1.m2.plus8
}

splitsh $1
