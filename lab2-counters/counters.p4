/*
 * counters.p4
 *
 * Lab 2 - Contadores y Estadisticas de Trafico
 * Curso de Redes de Computadoras - CI-0121
 *
 *   1. Un direct_counter por entrada de la tabla "flow_stats", donde
 *      cada entrada corresponde a un flujo identificado por
 *      (IP origen, IP destino). Cuenta paquetes y bytes.
 *
 *   2. Cuatro contadores globales (indexados, no directos) que
 *      acumulan paquetes/bytes por protocolo: TCP, UDP, ICMP, OTROS.
 *
 *   3. Un register<bit<32>> que acumula bytes por flujo (mismo indice
 *      que la tabla de flujos) para poder detectar "flujos elefante":
 *      si el acumulado de un flujo supera un umbral configurable,
 *      se marca el paquete (metadato is_elephant) para que el
 *      control plane pueda verlo y reaccionar (loggearlo, alertar, etc).
 *
 * El switch reenvia el paquete por el puerto contrario al de entrada.
 */

#include <core.p4>
#include <v1model.p4>

/*Constantes */

const bit<16> TYPE_IPV4 = 0x0800;

const bit<8> PROTO_ICMP = 1;
const bit<8> PROTO_TCP  = 6;
const bit<8> PROTO_UDP  = 17;

/* Indices fijos para el contador global por protocolo (counter de tamaño 4) */
const bit<32> IDX_TCP   = 0;
const bit<32> IDX_UDP   = 1;
const bit<32> IDX_ICMP  = 2;
const bit<32> IDX_OTHER = 3;

/* Tamano de la tabla de flujos = tamaño del register de bytes acumulados */
const bit<32> FLOW_TABLE_SIZE = 1024;

/* Umbral de bytes acumulados por flujo a partir del cual se considera
 * "flujo elefante". Se deja como valor por defecto razonable para trafico
 * de prueba.
 */
const bit<32> ELEPHANT_THRESHOLD_BYTES = 100000;

/*Headers */

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

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

header tcp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<32> seqNo;
    bit<32> ackNo;
    bit<4>  dataOffset;
    bit<3>  reserved;
    bit<9>  flags;
    bit<16> window;
    bit<16> checksum;
    bit<16> urgentPtr;
}

header udp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<16> length;
    bit<16> checksum;
}

header icmp_t {
    bit<8>  type;
    bit<8>  code;
    bit<16> checksum;
    bit<16> identifier;
    bit<16> seqNumber;
}

struct metadata {
    bool    is_elephant; /* marcado por la logica de elefante, visible al control plane via clone/log */
    bit<32> flow_bytes;  /* valor acumulado leido del register, para uso interno */
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
    tcp_t      tcp;
    udp_t      udp;
    icmp_t     icmp;
}

/*Parser*/

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
        transition select(hdr.ipv4.protocol) {
            PROTO_TCP:  parse_tcp;
            PROTO_UDP:  parse_udp;
            PROTO_ICMP: parse_icmp;
            default:    accept;
        }
    }

    state parse_tcp {
        packet.extract(hdr.tcp);
        transition accept;
    }

    state parse_udp {
        packet.extract(hdr.udp);
        transition accept;
    }

    state parse_icmp {
        packet.extract(hdr.icmp);
        transition accept;
    }
}

/*Checksum verificación*/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { /* No se valida el checksum: este programa solo observa trafico,
               no se espera que descarte paquetes por error de checksum. */ }
}

/*Ingress processing*/

control MyIngress(inout headers hdr,
                   inout metadata meta,
                   inout standard_metadata_t standard_metadata) {

    /*Contadores globales por protocolo (indexados, tamaño 4)*/
    counter(4, CounterType.packets_and_bytes) protocol_counter;

    /*Contador directo asociado a la tabla de flujos*/
    direct_counter(CounterType.packets_and_bytes) flow_counter;

    /*Registro de bytes acumulados por flujo, para deteccion de
     *flujo elefante. Mismo tamaño que la tabla de flujos.*/
    register<bit<32>>(FLOW_TABLE_SIZE) flow_byte_accum;

    /* Esta accion que se ejecuta cuando (srcAddr, dstAddr) coincide con una
     * entrada conocida de la tabla de flujos. El indice se usa tanto
     * para el register de acumulado de bytes como para identificar el
     * flujo de cara al control plane, debe coincidir con el indice
     * lógico de la entrada*/
    action count_flow(bit<32> flow_index) {
        flow_counter.count();

        /* Acumular bytes de este flujo en el register indicado */
        bit<32> prev;
        flow_byte_accum.read(prev, flow_index);
        bit<32> new_total = prev + (bit<32>) standard_metadata.packet_length;
        flow_byte_accum.write(flow_index, new_total);

        /* Marcar como elefante si se supera el umbral configurado */
        if (new_total > ELEPHANT_THRESHOLD_BYTES) {
            meta.is_elephant = true;
        }
        meta.flow_bytes = new_total;
    }

    action no_match() {
        /* Flujo no instalado explicitamente por el control plane:
         * no se actualiza el direct_counter (no hay "entry" que matchee),
         * pero igual se cuenta a nivel de protocolo en otra tabla. */
        NoAction();
    }

    /* Tabla principal de flujos:
     * El control plane es quien decide que flujos monitorear de forma
     * explicita (asignandoles un flow_index), con contadores directos 
     * asociados a flujos definidos por IP origen + IP destino". */
    table flow_stats {
        key = {
            hdr.ipv4.srcAddr: exact;
            hdr.ipv4.dstAddr: exact;
        }
        actions = {
            count_flow;
            no_match;
        }
        size = FLOW_TABLE_SIZE;
        default_action = no_match();
        counters = flow_counter;
    }

    /* Accion auxiliar que clasifica el protocolo y actualiza el
     * contador global correspondiente. */
    action bump_protocol_counter(bit<32> idx) {
        protocol_counter.count(idx);
    }

    /* Reenvio simple tipo "bump in the wire": puerto 1 - puerto 2.*/
    action forward(egressSpec_t port) {
        standard_metadata.egress_spec = port;
    }

    action drop() {
        mark_to_drop(standard_metadata);
    }

    /* Tabla de reenvio basada en la MAC de destino.
     * El controlador instala una entrada por cada host conocido,
     * mapeando MAC destino - puerto de salida. */
    table l2_forward {
        key = {
            hdr.ethernet.dstAddr: exact;
        }
        actions = {
            forward;
            drop;
        }
        size = 16;
        default_action = drop();
    }

    apply {
        if (hdr.ipv4.isValid()) {

            /* 1- Clasificacion por protocolo - contador global */
            if (hdr.tcp.isValid()) {
                bump_protocol_counter(IDX_TCP);
            } else if (hdr.udp.isValid()) {
                bump_protocol_counter(IDX_UDP);
            } else if (hdr.icmp.isValid()) {
                bump_protocol_counter(IDX_ICMP);
            } else {
                bump_protocol_counter(IDX_OTHER);
            }

            /* 2- Contador directo por flujo (IP origen + IP destino) y
             *    actualizacion del register para deteccion de elefante */
            flow_stats.apply();
        }

        /* 3 - Reenvio del paquete segun el puerto de entrada */
        l2_forward.apply();
    }
}

/*egress processing*/

control MyEgress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {
    apply {}
}

/*checksum*/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        /* El paquete no se modifica (no se reescribe TTL, MAC, etc.),
         * por lo que el checksum original sigue siendo valido y no es
         * necesario recalcularlo. */
    }
}

/*DEparser*/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.tcp);
        packet.emit(hdr.udp);
        packet.emit(hdr.icmp);
    }
}

/*Switch*/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
