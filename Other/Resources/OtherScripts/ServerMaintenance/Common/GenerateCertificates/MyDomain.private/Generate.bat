openssl genrsa -out MyDomain.private.key 4096
openssl req -new -subj "/C=DE/ST=MyS/L=MyL/O=MyO/CN=MyDomain.private" -x509 -key MyDomain.private.key -out MyDomain.private.unsigned.crt -days 365000
openssl pkcs12 -export -out MyDomain.private.unsigned.pfx -password pass:4X35cfe6ddb_39476fa868627ea473ff9e -inkey MyDomain.private.key -in MyDomain.private.unsigned.crt