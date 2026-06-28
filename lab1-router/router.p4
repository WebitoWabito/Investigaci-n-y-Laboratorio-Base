// router.p4 — Lab 1: Router IPv4 Estático
//
// Programa P4_16 para BMv2/v1model.
// Implementa un router IPv4 básico con:
//   - Parser Ethernet + IPv4.
//   - Tabla LPM para selección de ruta.
//   - Reescritura de MAC origen/destino.
//   - Selección de puerto de salida.
//   - Decremento de TTL.
//   - Descarte si no hay ruta o si TTL está agotado.
//   - Recalculo del checksum IPv4 después de modificar el TTL.

#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4 = 0x0800;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

/*************************************************************************
******************************* HEADERS **********************************
*************************************************************************/

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    /* No se requiere metadata adicional para este laboratorio. */
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

/*************************************************************************
******************************** PARSER **********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default:   accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }
}

/*************************************************************************
*************************** CHECKSUM VERIFY ******************************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {
        /* Para este laboratorio no se valida el checksum de entrada. */
    }
}

/*************************************************************************
****************************** INGRESS ***********************************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    /** Descarta el paquete. */
    action drop() {
        mark_to_drop(standard_metadata);
    }

    /**
     * Reenvía un paquete IPv4.
     * El controlador instala la MAC destino, MAC origen y puerto de salida.
     */
    action ipv4_forward(macAddr_t dstAddr, macAddr_t srcAddr, egressSpec_t port) {
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ethernet.srcAddr = srcAddr;
        standard_metadata.egress_spec = port;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    /**
     * Tabla LPM del router.
     * Las entradas se instalan desde controller.py, no están quemadas en P4.
     */
    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            ipv4_forward;
            drop;
            NoAction;
        }
        size = 1024;
        default_action = drop();
    }

    apply {
        if (hdr.ipv4.isValid()) {
            // Si el TTL llega a 1, el paquete se descarta para evitar loops.
            if (hdr.ipv4.ttl > 1) {
                ipv4_lpm.apply();
            } else {
                drop();
            }
        } else {
            // Este router solo procesa IPv4.
            drop();
        }
    }
}

/*************************************************************************
******************************* EGRESS ***********************************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply {
        /* No se requiere procesamiento de salida. */
    }
}

/*************************************************************************
************************** CHECKSUM COMPUTE ******************************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(
            hdr.ipv4.isValid(),
            {
                hdr.ipv4.version,
                hdr.ipv4.ihl,
                hdr.ipv4.diffserv,
                hdr.ipv4.totalLen,
                hdr.ipv4.identification,
                hdr.ipv4.flags,
                hdr.ipv4.fragOffset,
                hdr.ipv4.ttl,
                hdr.ipv4.protocol,
                hdr.ipv4.srcAddr,
                hdr.ipv4.dstAddr
            },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16
        );
    }
}

/*************************************************************************
****************************** DEPARSER **********************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

/*************************************************************************
******************************** SWITCH **********************************
*************************************************************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
