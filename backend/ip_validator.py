import ipaddress
import logging

logger = logging.getLogger(__name__)

def is_ip_allowed(client_ip: str, allowed_cidrs: list[str]) -> bool:
    """
    Checks if a given client IP address belongs to any of the allowed CIDR networks.
    
    Args:
        client_ip (str): The IP address of the client request.
        allowed_cidrs (list[str]): List of CIDR strings like ['192.168.1.0/24', '10.0.0.0/8']
        
    Returns:
        bool: True if the IP is within any of the networks, False otherwise.
    """
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        logger.error(f"Invalid IP address format received: {client_ip}")
        return False

    for cidr_str in allowed_cidrs:
        try:
            network = ipaddress.ip_network(cidr_str, strict=False)
            if ip in network:
                return True
        except ValueError:
            logger.error(f"Invalid CIDR format in database: {cidr_str}")
            continue
            
    return False
