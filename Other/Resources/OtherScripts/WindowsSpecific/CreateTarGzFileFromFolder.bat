set "destinationFolder=%*"
7zg a -ttar "archive.tar" "%destinationFolder%"
7zg a -tgzip archive.tar.gz "%destinationFolder%\archive.tar"
del archive.tar