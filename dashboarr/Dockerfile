# Use tiny Alpine base
FROM alpine:latest

# Install lighttpd (small, ~1MB)
RUN apk add --no-cache lighttpd

# Copy dashboard files into the web root
COPY . /var/www/localhost/htdocs/

# Expose port 80
EXPOSE 80

# Start lighttpd in foreground
CMD ["lighttpd", "-D", "-f", "/etc/lighttpd/lighttpd.conf"]
