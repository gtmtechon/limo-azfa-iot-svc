# function_app.py

import logging
import json
import os
import azure.functions as func

# SendGrid 라이브러리 임포트 (MaintenanceScheduler 함수에 필요)
# 본 데모에서는 실제 메일은 보내지 않고, 메시지만 로깅합니다.
# 실제로 SendGrid를 사용하려면 아래 주석을 해제하고, 필요한 환경 변수를 설정하세요.
# 예: SENDGRID_API_KEY, SENDER_EMAIL, RECIPIENT_EMAIL
# import sendgrid
# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail, Email, Personalization

logger = logging.getLogger(__name__)

# 중요: func.FunctionApp() 인스턴스는 프로젝트 전체에서 단 한 번만 정의되어야 합니다.
# 이 파일의 최상단에 위치하는 것이 일반적입니다.
app = func.FunctionApp()

COSMOS_DB_DATABASE = os.getenv("CosmosDBDatabase", "RobotMonitoringDB")
COSMOS_DB_CONTAINER = os.getenv("CosmosDBContainer", "LatestRobotStates")
COSMOS_DB_CONNECTION_STRING = os.getenv("CosmosDBConnection")
                                        
# ==============================================================================
# 1. RobotStatusChangeLogger 함수 (Event Grid Trigger)
# 모든 로봇 상태 변경 이벤트를 수신하여 로그를 기록합니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
def RobotStatusChangeLogger(event: func.EventGridEvent):
    logger.info('Python Event Grid trigger processed RobotStatusChangeLogger event.')
    
    try:
        event_data = event.get_json()
        robot_telemetry_body = event_data.get('data', {}).get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Logger: Event body is empty or malformed: {event_data}")
            return

        device_id = robot_telemetry_body.get('deviceId', 'N/A')
        battery_level = robot_telemetry_body.get('batteryLevel', 'N/A')
        current_status = robot_telemetry_body.get('currentStatus', 'N/A')
        ttimestamp = robot_telemetry_body.get('ttimestamp', 'N/A')

        log_message = (
            f"RobotTelemetryLog - DeviceId: {device_id}, "
            f"Timestamp: {ttimestamp}, "
            f"Battery: {battery_level}%, Status: {current_status}"
        )
        logger.info(log_message)

    except json.JSONDecodeError:
        logger.error(f"Logger: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Logger: Error processing Event Grid event: {e}", exc_info=True)


# ==============================================================================
# 2. MaintenanceScheduler 함수 (Event Grid Trigger)
# 특정 조건(배터리, 상태)을 만족하는 이벤트에 대해 알림을 보냅니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
def MaintenanceScheduler(event: func.EventGridEvent):
    logger.info('Python Event Grid trigger processed MaintenanceScheduler event.')
    
    try:
        event_data = event.get_json()
        robot_telemetry_body = event_data.get('data', {}).get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Scheduler: Event body is empty or malformed: {event_data}")
            return

        device_id = robot_telemetry_body.get('deviceId', 'N/A')
        battery_level = robot_telemetry_body.get('batteryLevel')
        current_status = robot_telemetry_body.get('currentStatus', 'N/A')
        ttimestamp = robot_telemetry_body.get('ttimestamp', 'N/A')
        
        # 알림 트리거 조건
        alert_triggered = False
        alert_reason = []

        if battery_level is not None and battery_level < 20:
            alert_triggered = True
            alert_reason.append(f"배터리 잔량 {battery_level}% 미만")

        if current_status.lower() == 'error':
            alert_triggered = True
            alert_reason.append(f"현재 상태 '{current_status}' (에러)")

        if alert_triggered:
            alert_subject = f"[긴급 알림] 로봇 {device_id} - 유지보수 필요!"
            alert_content = (
                f"로봇 ID: {device_id} (시간: {ttimestamp})\n"
                f"이유: {', '.join(alert_reason)}\n"
                f"현재 배터리: {battery_level}%, 상태: {current_status}\n\n"
                "자세한 내용은 호수 수질 관리 시스템을 확인해주세요."
            )
            
            logger.critical(f"Scheduler: Alert triggered for robot {device_id}: {alert_content}")

            # 이메일 발송 로직 (SendGrid)
        #     try:
        #         sg = sendgrid.SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        #         mail = Mail()
        #         mail.from_email = Email(os.environ.get('SENDER_EMAIL', 'sender@example.com'))
                
        #         personalization = Personalization()
        #         personalization.add_to(Email(os.environ.get('RECIPIENT_EMAIL', 'recipient@example.com')))
        #         mail.add_personalization(personalization)
                
        #         mail.subject = alert_subject
        #         mail.add_content("text/plain", alert_content)
                
        #         response = sg.send(mail)
        #         logger.info(f"Scheduler: Email sent. Status Code: {response.status_code}")
        #     except Exception as e:
        #         logger.error(f"Scheduler: Error sending email via SendGrid: {e}")
        # else:
        #     logger.info(f"Scheduler: No alert triggered for robot {device_id} (Battery: {battery_level}%, Status: {current_status})")

    except json.JSONDecodeError:
        logger.error(f"Scheduler: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Scheduler: Error processing Event Grid event: {e}", exc_info=True)


# ==============================================================================
# 3. RobotStateUpdater 함수 (Event Grid Trigger + Cosmos DB Output Binding)
# 로봇 상태 변경 이벤트를 수신하여 Cosmos DB에 실시간으로 업데이트합니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
@app.cosmos_db_output(arg_name="outputDocument", 
                      database_name=COSMOS_DB_DATABASE,
                      collection_name=COSMOS_DB_CONTAINER,
                      connection_string_setting=COSMOS_DB_CONNECTION_STRING,
                      create_if_not_exists=False # 배포 환경에서는 False로 설정하는 것이 좋습니다.
                     )
def RobotStateUpdater(event: func.EventGridEvent, outputDocument: func.Out[func.Document]):
    logger.info('Python Event Grid trigger processed RobotStateUpdater event.')

    try:
        event_data = event.get_json()
        robot_telemetry_body = event_data.get('data', {}).get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Updater: Event body is empty or malformed: {event_data}")
            return

        # Cosmos DB에 저장할 문서 생성 (id는 upsert를 위해 deviceId로 설정)
        robot_document = {
            "id": robot_telemetry_body.get('deviceId'),
            "deviceId": robot_telemetry_body.get('deviceId'),
            "timestamp": robot_telemetry_body.get('ttimestamp'),
            "batteryLevel": robot_telemetry_body.get('batteryLevel'),
            "currentStatus": robot_telemetry_body.get('currentStatus'),
            "purificationStatus": robot_telemetry_body.get('purificationStatus'),
            "location": robot_telemetry_body.get('location'),
            "eventGridEventId": event.id
        }
        
        # Output Binding을 통해 문서 저장/업데이트
        # func.Document.from_json()을 사용하여 JSON 문자열을 func.Document 객체로 변환
        outputDocument.set(func.Document.from_json(json.dumps(robot_document)))
        logger.info(f"Updater: Updated Cosmos DB for DeviceId: {robot_document['deviceId']}")

    except json.JSONDecodeError:
        logger.error(f"Updater: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Updater: Error processing Event Grid event: {e}", exc_info=True)
    