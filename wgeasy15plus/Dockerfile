FROM ghcr.io/wg-easy/wg-easy:15.3.0

RUN apk add --no-cache nginx jq nftables && \
    ln -sf xtables-nft-multi /usr/sbin/iptables && \
    ln -sf xtables-nft-multi /usr/sbin/iptables-save && \
    ln -sf xtables-nft-multi /usr/sbin/iptables-restore && \
    ln -sf xtables-nft-multi /usr/sbin/ip6tables && \
    ln -sf xtables-nft-multi /usr/sbin/ip6tables-save && \
    ln -sf xtables-nft-multi /usr/sbin/ip6tables-restore

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
